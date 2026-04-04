"""
Pipeline Bridge — Agent Interactions Mixin (gates, hooks, scouts, cron).
管線橋接器 — Agent 交互 Mixin（門控、鉤子、Scout、Cron）。

Split from pipeline_bridge.py (TD-01) to stay under 1200-line limit.
"""
from __future__ import annotations

import json as _json_mod
import logging
from typing import Any

# T2.07: Import Scout-related enums for local market scanning
# Lazy import pattern to avoid circular dependencies
# 懒惰导入模式避免循环依赖
try:
    from .multi_agent_framework import DataQualityLevel, SentimentScore
except ImportError:
    # If multi_agent_framework is not available, define fallback enums
    class DataQualityLevel:  # type: ignore
        FACT = "fact"
        INFERENCE = "inference"
        HYPOTHESIS = "hypothesis"

    class SentimentScore:  # type: ignore
        POSITIVE = "positive"
        NEGATIVE = "negative"
        NEUTRAL = "neutral"

logger = logging.getLogger(__name__)


class _BridgeAgentsMixin:
    """Agent interaction methods for PipelineBridge — gates, hooks, scout scans, cron triggers."""

    def _gate_intent(
        self,
        intent: Any,
        market_prices: dict[str, float],
        _local_stats: dict[str, int],
        _local_guardian: dict[str, int],
    ) -> tuple[float, float | None, float] | None:
        """
        Run all pre-submission gate checks on a single intent.
        對單個意圖執行所有提交前門控檢查。

        Gate pipeline (in order):
          1. Perception plane cognitive honesty check (Principle 10)
          2. H0 Gate deterministic filter — fail-closed (Principle 5: survival > profit)
          3. Governance Hub authorization — fail-closed
          4. Cost gate — ATR vs round-trip cost check — fail-open (Principle 13)
          5. Dynamic qty calculation + exchange rounding
          6. Guardian Agent verdict — fail-closed (DOC-01 §5.6)
          7. Edge filter — advisory only (logged, not blocking)

        門控管線（按順序）：
          1. 感知平面認知誠實檢查（原則 10）
          2. H0 確定性過濾 — fail-closed（原則 5：生存 > 利潤）
          3. 治理授權 — fail-closed
          4. 動態數量計算 + 交易所精度四捨五入
          5. Guardian 裁決 — fail-closed（DOC-01 §5.6）
          6. Edge 過濾 — 僅建議（記錄但不阻塞）

        Returns:
            (submit_qty, submit_leverage, effective_leverage) if approved.
            None if the intent was rejected by any gate (already logged + stats bumped).
        返回：
            若批准：(submit_qty, submit_leverage, effective_leverage)。
            若被任何門控拒絕：None（已記錄日誌並更新統計）。
        """
        def _bump(counter: dict, key: str, amount: int = 1) -> None:
            """Increment a local counter (no lock needed). / 累加本地计数器（无需锁）。"""
            counter[key] = counter.get(key, 0) + amount

        # T2.02: Cognitive honesty check (perception plane validation)
        # 认知诚实检查（感知平面验证）
        if self._perception_plane:
            data_id = getattr(intent, "perception_data_id", None)
            if data_id:
                # Intent references perception data — validate before proceeding
                # 意图引用了感知数据 — 在继续前验证
                eligible, reason = self._perception_plane.validate_for_decision(data_id)
                if not eligible:
                    logger.info(
                        "Intent rejected by perception honesty: %s %s (reason: %s) / 意图被感知拒絕",
                        intent.symbol, intent.side, reason
                    )
                    _bump(_local_stats, "intents_rejected")
                    self._mark_intent(intent, "rejected_perception")
                    return None
            else:
                # Intent has no perception data marked (implicit FACT assumption for exchange data)
                # 意图无感知数据标记（假设交易所数据为 FACT）
                # This is acceptable for exchange-sourced signals
                pass

        # ── 0A-1: Apply learning feedback weights from StrategistAgent ──
        # 0A-1：應用 StrategistAgent 的學習反饋權重（模式洞察 → 策略偏好）
        # Pattern insights adjust strategy weights in [0.2, 2.0]; multiply into confidence.
        # Fail-open: if StrategistAgent unavailable, weight defaults to 1.0 (neutral).
        # 模式洞察調整策略權重 [0.2, 2.0]，乘入 confidence。
        # Fail-open：StrategistAgent 不可用時，權重默認 1.0（中性）。
        if self._strategist_agent is not None:
            try:
                _strategy_name = getattr(intent, "strategy_name", "") or ""
                _learning_weight = self._strategist_agent.get_strategy_weight(_strategy_name)
                if _learning_weight != 1.0:
                    _old_conf = getattr(intent, "confidence", None)
                    if _old_conf is not None and isinstance(_old_conf, (int, float)):
                        _new_conf = max(0.0, min(1.0, _old_conf * _learning_weight))
                        intent.confidence = _new_conf
                        logger.debug(
                            "0A-1: Learning weight applied to %s/%s: %.2f × %.2f = %.2f / "
                            "學習權重已應用：置信度 %.2f × 權重 %.2f = %.2f",
                            intent.symbol, _strategy_name,
                            _old_conf, _learning_weight, _new_conf,
                            _old_conf, _learning_weight, _new_conf,
                        )
            except Exception as _lw_err:
                # fail-open: learning weight error is non-fatal / 學習權重異常不阻塞
                logger.debug("0A-1: Learning weight lookup failed (fail-open): %s", _lw_err)

        # ── Sprint 5a: H0 Gate blocking — fail-closed (principle 5: survival > profit) ──
        # Sprint 5a：H0 Gate 阻擋模式 — fail-closed（根原則 5：生存 > 利潤）
        # H0 Gate blocking: stale data or unhealthy system state → reject intent entirely.
        # This is activated in Sprint 5a after H0 Gate SLA validation and Day 3 integration
        # confirmed the gate is safe to enforce. Previously warn-only (paper mode), now
        # fully blocking to protect against trading on bad market data.
        # H0 Gate 阻擋：數據過期或系統不健康時拒絕 intent，防止基於錯誤市場數據交易。
        # Sprint 5a 之前為 warn-only（paper 模式），現已切換為全面阻擋。
        if self._h0_gate is not None:
            try:
                _h0_category = (
                    intent.metadata.get("category", "linear")
                    if hasattr(intent, "metadata") and intent.metadata
                    else "linear"
                )
                _h0_result = self._h0_gate.check(intent.symbol, _h0_category)
                if not _h0_result.allowed:
                    # H0 Gate blocking — fail-closed to protect against stale/unhealthy market data
                    # H0 Gate 阻擋模式 — 數據過期或系統不健康時拒絕意圖，原則 5（生存 > 利潤）
                    _bump(_local_stats, "intents_h0_blocked")
                    logger.warning(
                        "H0Gate BLOCKED intent %s %s check=%s reason=%s latency=%dμs"
                        " / H0 門控已拒絕 intent：%s %s",
                        intent.symbol,
                        getattr(intent, "side", "?"),
                        _h0_result.check_name,
                        _h0_result.reason,
                        _h0_result.latency_us,
                        intent.symbol,
                        getattr(intent, "side", "?"),
                    )
                    self._mark_intent(intent, "blocked_h0")
                    return None  # skip this intent, do not submit
            except Exception as _h0_check_err:
                # ARCH-4 fix: fail-closed on H0 Gate exception (DOC-01 §5.6: survival > profit)
                # ARCH-4 修復：H0 門控異常時 fail-closed（根原則 5：生存 > 利潤）
                logger.error(
                    "H0Gate check error — fail-closed, rejecting intent: %s "
                    "/ H0 門控檢查異常 — fail-closed，拒絕 intent",
                    _h0_check_err,
                )
                _bump(_local_stats, "intents_h0_blocked")
                self._mark_intent(intent, "blocked_h0_error")
                return None

        # Governance Hub authorization check / 治理集線器授權檢查
        if self._governance_hub:
            try:
                if not self._governance_hub.is_authorized():
                    logger.info(
                        "Intent rejected by governance: %s %s (not authorized) / 意图被治理拒絕",
                        intent.symbol, intent.side
                    )
                    _bump(_local_stats, "intents_rejected")
                    self._mark_intent(intent, "rejected_governance")
                    return None
            except Exception as exc:
                logger.error("Governance is_authorized error — fail-closed: %s", exc)
                _bump(_local_stats, "intents_rejected")
                self._mark_intent(intent, "rejected_governance")
                return None

        # ── U-04: Cost-aware entry gate (deterministic, fail-open) ──
        # U-04：成本感知入場門檻（確定性規則，數據缺失時 fail-open）
        # Reject entries where expected volatility (ATR%) is too low to cover round-trip costs.
        # 當預期波動率（ATR%）不足以覆蓋來回交易成本時拒絕開倉。
        if self._cost_gate_enabled:
            try:
                from local_model_tools.cost_gate import should_reject_for_cost
                _atr_pct = self._get_atr_pct_for_cost_gate(intent.symbol)
                _volume_24h = self._get_volume_24h(intent.symbol)
                _cost_reject, _cost_reason = should_reject_for_cost(
                    symbol=intent.symbol,
                    atr_pct=_atr_pct,
                    win_rate=0.5,  # default; future: dynamic from round-trip stats
                    daily_trade_count=self._daily_trade_count,
                    volume_24h=_volume_24h,
                )
                if _cost_reject:
                    _bump(_local_stats, "intents_cost_rejected")
                    logger.warning(
                        "Cost gate rejected %s %s: %s / 成本門檻拒絕",
                        intent.symbol, getattr(intent, "side", "?"), _cost_reason,
                    )
                    self._mark_intent(intent, "rejected_cost_gate")
                    return None
            except Exception as _cost_err:
                # ARCH-4 fix: fail-closed on cost gate exception (DOC-01 §5.6: survival > profit)
                # ARCH-4 修復：成本門檻異常時 fail-closed（根原則 5：生存 > 利潤）
                logger.error(
                    "Cost gate error — fail-closed, rejecting intent: %s "
                    "/ 成本門檻異常 — fail-closed，拒絕 intent",
                    _cost_err,
                )
                _bump(_local_stats, "intents_cost_rejected")
                self._mark_intent(intent, "rejected_cost_gate_error")
                return None

        # ── Batch 8: Guardian Agent as PRIMARY gate (fail-closed) ──
        # Batch 8：Guardian Agent 作为主门控（fail-closed）
        # Guardian verdict overrides all other filters (EX-06 §9).
        # If Guardian is unavailable → REJECTED (fail-closed, DOC-01 §5.6).
        # Original edge filter demoted to auxiliary reference (logged only).
        # Dynamic qty: recalculate based on current balance at submission time
        # 動態倉位：在提交時根據當前餘額重新計算
        _submit_qty = intent.qty
        if self._auto_deployer and market_prices.get(intent.symbol):
            try:
                _submit_qty = self._auto_deployer.compute_dynamic_qty(
                    intent.symbol, market_prices[intent.symbol]
                )
            except Exception:
                logger.debug("Dynamic qty fallback to intent.qty for %s", intent.symbol)

        # Round qty to exchange step precision (shared with Demo connector)
        # 統一四捨五入到交易所步長精度（與 Demo connector 共用）
        # Ensures Paper and Demo receive identical qty values.
        # INV-3: Pass category so inverse contracts round to integer contracts.
        # INV-3：傳入 category，確保 inverse 合約正確取整（整數張數）。
        try:
            from .bybit_demo_connector import round_qty_for_exchange
            _intent_category = (
                intent.metadata.get("category", "linear")
                if hasattr(intent, "metadata") and intent.metadata
                else "linear"
            )
            _submit_qty = round_qty_for_exchange(_submit_qty, category=_intent_category)
            if _submit_qty <= 0:
                logger.info("Qty rounds to zero for %s, skipping / qty 四捨五入為零，跳過", intent.symbol)
                self._mark_intent(intent, "rejected_qty_zero")
                return None
        except ImportError:
            pass  # Demo connector not available, use raw qty

        _submit_leverage = None  # may be overridden by Guardian MODIFIED verdict

        if self._guardian_agent:
            try:
                from .multi_agent_framework import TradeIntent as _TI, RiskVerdictResult as _RVR

                # Sync active positions to Guardian for context
                # 同步活跃仓位到 Guardian 用于上下文判断
                if self._open_positions:
                    self._guardian_agent.update_active_positions(self._open_positions)

                # Build TradeIntent from OrderIntent / 从 OrderIntent 构建 TradeIntent
                _direction = "long" if intent.side == "Buy" else "short"
                _strategy = (
                    intent.metadata.get("strategy_name", "unknown")
                    if intent.metadata else "unknown"
                )
                _ti = _TI(
                    symbol=intent.symbol,
                    strategy=_strategy,
                    direction=_direction,
                    size=intent.qty,
                    params={"leverage": getattr(intent, "leverage", 1.0) or 1.0},
                    confidence=getattr(intent, "confidence", 0.5) or 0.5,
                )

                verdict = self._guardian_agent.review_intent(_ti)

                _bump(_local_guardian, "checked")

                if verdict.result == _RVR.REJECTED:
                    _bump(_local_guardian, "rejected")
                    _bump(_local_stats, "intents_rejected")
                    logger.info(
                        "Intent REJECTED by Guardian: %s %s (reason: %s, risk=%.2f) / "
                        "意图被 Guardian 拒绝",
                        intent.symbol, intent.side, verdict.reason, verdict.risk_score,
                    )
                    self._mark_intent(intent, "rejected_guardian")
                    return None

                elif verdict.result == _RVR.MODIFIED:
                    _bump(_local_guardian, "modified")
                    # Apply modifications: adjust qty and/or leverage
                    # 应用修改：调整数量和/或杠杆
                    if "size" in verdict.modified_params:
                        _submit_qty = float(verdict.modified_params["size"])
                    if "leverage" in verdict.modified_params:
                        _submit_leverage = float(verdict.modified_params["leverage"])
                    logger.info(
                        "Intent MODIFIED by Guardian: %s %s (qty %.6f→%.6f, reason: %s) / "
                        "意图被 Guardian 修改",
                        intent.symbol, intent.side, intent.qty, _submit_qty, verdict.reason,
                    )
                else:
                    # APPROVED
                    _bump(_local_guardian, "approved")
                    logger.debug(
                        "Intent APPROVED by Guardian: %s %s / 意图被 Guardian 批准",
                        intent.symbol, intent.side,
                    )

            except Exception as _guardian_err:
                # Guardian error → fail-closed: REJECT (DOC-01 §5.6)
                # Guardian 错误 → fail-closed：拒绝
                logger.error(
                    "Guardian error — fail-closed REJECT: %s %s (%s) / "
                    "Guardian 异常 — fail-closed 拒绝",
                    intent.symbol, intent.side, _guardian_err,
                )
                _bump(_local_guardian, "errors")
                _bump(_local_stats, "intents_rejected")
                self._mark_intent(intent, "rejected_guardian")
                return None

        else:
            # P0-2 FIX: Guardian unavailable → fail-closed REJECT (DOC-01 §5.6)
            # Guardian 不可用 → fail-closed 拒绝
            logger.error(
                "Guardian unavailable — fail-closed REJECT: %s %s",
                getattr(intent, "symbol", "?"), getattr(intent, "side", "?")
            )
            _bump(_local_stats, "intents_rejected")
            self._mark_intent(intent, "rejected_no_guardian")
            return None

        # Resolve final effective leverage:
        # Guardian MODIFIED value > intent.metadata["leverage"] > intent.leverage attr > 1.0
        # 确定最终有效杠杆：Guardian 修改值 > metadata > intent 属性 > 默认 1.0
        _effective_leverage = float(
            _submit_leverage
            or (intent.metadata or {}).get("leverage")
            or getattr(intent, "leverage", None)
            or 1.0
        )

        # 5-B: L1 Pre-trade edge filter (auxiliary reference — logged but not blocking)
        # L1 交易前 edge 过滤（辅助参考 — 仅记录，不阻塞）
        # Batch 8: Guardian is now the primary gate; edge filter demoted to advisory
        # Batch 8：Guardian 已成为主门控；edge filter 降级为参考
        if self._ollama_client and self._edge_filter_enabled:
            edge_ok = self._check_edge_filter(intent, market_prices)
            if not edge_ok:
                logger.info(
                    "Edge filter advisory: would reject %s %s (Guardian already approved) / "
                    "Edge 过滤器建议：会拒绝 %s %s（Guardian 已批准）",
                    intent.symbol, intent.side, intent.symbol, intent.side,
                )
                # Note: no longer blocking — Guardian verdict is authoritative
                # 注意：不再阻塞 — Guardian 裁决为权威

        return (_submit_qty, _submit_leverage, _effective_leverage)

    def _post_execution_hooks(
        self,
        intent: Any,
        result: Any,
        _submit_qty: float,
        _effective_leverage: float,
        category: str,
        market_prices: dict[str, float],
        _local_stats: dict[str, int],
    ) -> None:
        """
        Handle everything after Paper engine submit_order() returns.
        處理 Paper 引擎 submit_order() 返回後的所有事項。

        Responsibilities:
          - Classify result as accepted/rejected and update stats + intent status
          - On accepted fill: track position open or detect round-trip close
          - Notify auto-deployer of fills (strategy position state sync)
          - Sync to Bybit Demo (mirror paper, fail-open for Demo errors)
          - Fire Telegram alert for market orders

        職責：
          - 將結果分類為已接受/已拒絕，更新統計和意圖狀態
          - 成交時：追蹤開倉或偵測交易回合完成
          - 通知自動部署器成交情況（策略倉位狀態同步）
          - 同步到 Bybit Demo（鏡像 Paper，Demo 錯誤 fail-open）
          - 市價單發送 Telegram 告警
        """
        def _bump(counter: dict, key: str, amount: int = 1) -> None:
            """Increment a local counter (no lock needed). / 累加本地计数器（无需锁）。"""
            counter[key] = counter.get(key, 0) + amount

        order = result.get("order", {}) if isinstance(result, dict) else {}
        rejected = result.get("rejected_reason") if isinstance(result, dict) else None

        if rejected:
            _bump(_local_stats, "intents_rejected")
            self._mark_intent(intent, "rejected_risk")
            logger.info(
                "Intent rejected: %s %s %s qty=%.6f reason=%s / 意图被拒",
                intent.symbol, intent.side, intent.order_type,
                intent.qty, rejected,
            )
            return

        _bump(_local_stats, "intents_accepted")
        # U-04: Increment daily trade counter for cost gate safety-valve
        # U-04：遞增每日成交計數器（成本門檻安全閥用）
        self._daily_trade_count += 1
        self._mark_intent(intent, "submitted")
        logger.info(
            "Intent submitted: %s %s %s qty=%.6f / 意图已提交",
            intent.symbol, intent.side, intent.order_type, intent.qty,
        )

        # ── Submit to Bybit Demo FIRST (before position tracking) ──
        # Demo 必須先於持倉追蹤提交，這樣 _on_position_open 才能查到 Demo 成交價
        # Demo submission must happen before position tracking so that
        # _on_position_open can query Demo's actual fill price for stop-loss.
        _demo_synced = False
        if self._demo_connector and self._demo_connector.is_enabled:
            # SPOT-DEMO: Bybit spot trades appear as wallet balance changes,
            # not as positions.  Comparing Paper spot positions against Demo
            # positions will always mismatch (Demo side is always empty).
            # Skip Demo submission for spot — track Paper-side only.
            # 现货交易在 Demo 端体现为余额变化而非持仓，跳过 Demo 提交，仅记录 Paper。
            if category == "spot":
                logger.debug(
                    "Skipping Demo submission for spot %s %s (spot=wallet-only on Demo) / "
                    "跳过现货 Demo 提交（现货体现为余额变化）",
                    intent.symbol, intent.side,
                )
                _bump(_local_stats, "demo_spot_skipped")
            else:
                try:
                    # Set leverage on Demo before placing the order so that
                    # margin math and PnL match Paper (Paper always uses
                    # _effective_leverage; Demo would otherwise keep whatever
                    # the Bybit account last had configured per-symbol).
                    # 在下单前先同步杠杆，确保 Demo 保证金计算与 Paper 一致。
                    self._demo_connector.set_leverage(
                        symbol=intent.symbol,
                        buy_leverage=_effective_leverage,
                        category=category,
                    )
                    demo_result = self._demo_connector.submit_order(
                        symbol=intent.symbol,
                        side=intent.side,
                        order_type="Market" if intent.order_type == "market" else "Limit",
                        qty=_submit_qty,
                        price=intent.price,
                        category=category,
                    )
                    if demo_result.get("retCode") == 0:
                        _demo_synced = True
                    else:
                        logger.warning(
                            "Demo order REJECTED: %s %s qty=%.6f reason=%s — Paper/Demo DIVERGED / "
                            "Demo 訂單被拒：Paper 已接受但 Demo 拒絕，數據已分歧",
                            intent.symbol, intent.side, _submit_qty,
                            demo_result.get("retMsg"),
                        )
                except Exception as _demo_err:
                    logger.warning(
                        "Demo connector error: %s %s — %s — Paper/Demo DIVERGED / "
                        "Demo 連接異常：數據已分歧",
                        intent.symbol, intent.side, _demo_err,
                    )
                # Track sync status in local counters (flushed at end)
                # 在本地计数器中追踪同步状态（最后一次性刷入）
                if _demo_synced:
                    _bump(_local_stats, "demo_synced")
                else:
                    _bump(_local_stats, "demo_diverged")

        # H1: track position or detect close for E1/G1 hooks
        # H1：追踪持仓，或检测关闭触发 E1/G1
        fills = result.get("fills", []) if isinstance(result, dict) else []
        close_pnl = result.get("close_pnl", 0.0) if isinstance(result, dict) else 0.0
        if fills:
            fill = fills[0]
            fill_price = fill.get("price", market_prices.get(intent.symbol, 0.0))
            is_open_fill = close_pnl == 0.0
            if close_pnl != 0.0:
                # Position closed — round-trip complete
                # 持仓已关闭 — 一轮交易完成
                # U-05: Extract close fee from fill record for round-trip cost accounting.
                # U-05：从成交记录提取平仓费用用于 round-trip 成本核算。
                _close_fee = fill.get("fee", 0.0)
                self._on_round_trip_complete(intent, fill_price, close_pnl, close_fee=_close_fee)
            else:
                # New position opened — start tracking
                # 新持仓开仓 — 开始追踪（用 rounded qty 確保與 Demo 一致）
                # ★ FIX: 從 Demo 取得真實成交價，用於交易所條件止損單
                # Query Demo position avgPrice for accurate stop-loss trigger.
                # Market orders fill instantly on Bybit; position avgPrice is available.
                _demo_fill = 0.0
                if _demo_synced:
                    try:
                        _pos_resp = self._demo_connector.get_positions(
                            category=category, symbol=intent.symbol,
                        )
                        _pos_list = _pos_resp.get("result", {}).get("list", [])
                        for _p in _pos_list:
                            if _p.get("symbol") == intent.symbol and float(_p.get("size", 0)) > 0:
                                _demo_fill = float(_p.get("avgPrice", 0))
                                break
                        if _demo_fill > 0:
                            logger.debug(
                                "Demo fill price for %s: %.8f (Paper: %.8f) / "
                                "Demo 成交價：%.8f（Paper：%.8f）",
                                intent.symbol, _demo_fill, fill_price,
                                _demo_fill, fill_price,
                            )
                    except Exception as _demo_price_err:
                        logger.debug(
                            "Could not get Demo fill price for %s: %s — using Paper price / "
                            "無法取得 Demo 成交價，使用 Paper 價格",
                            intent.symbol, _demo_price_err,
                        )
                self._on_position_open(
                    intent, fill_price, actual_qty=_submit_qty,
                    demo_fill_price=_demo_fill,
                )
            # Sync strategy position state via on_fill callback
            # 通过 on_fill 回调同步策略仓位状态，防止意图态漂移
            if self._auto_deployer:
                strategy_name = getattr(intent, "strategy_name", None)
                if strategy_name:
                    fill_for_callback = {
                        "symbol": intent.symbol,
                        "side": intent.side,
                        "qty": intent.qty,
                        "price": fill_price,
                        "strategy_name": strategy_name,
                    }
                    self._auto_deployer.notify_fill(strategy_name, fill_for_callback, is_open_fill)

        if self._telegram and intent.order_type == "market":
            price = market_prices.get(intent.symbol, 0)
            self._telegram.alert_trade(intent.symbol, intent.side, _submit_qty, price, getattr(intent, "reason", "")[:100])

    def _check_stops(self) -> None:
        """Check stop-losses and submit close orders if triggered / 检查止损并提交平仓"""
        try:
            triggered = self._stop_mgr.check_stops(self._latest_prices)
        except Exception:
            logger.exception("StopManager check error / 止损检查异常")
            return

        market_prices = dict(self._latest_prices)
        for stop in triggered:
            try:
                # Guard: skip if position was already closed by RiskManager in the same tick.
                # Without this check, submitting a close-side order on a gone position would
                # open a new opposite-direction position — a silent bug.
                # 防止双重止损：若 RiskManager 已平仓，跳过此止损单，避免开出反向仓位。
                try:
                    engine_state = self._engine.get_state()
                    if not engine_state.get("positions", {}).get(stop["symbol"]):
                        logger.debug(
                            "Stop skipped — position already closed: %s / 止损跳过，仓位已平",
                            stop["symbol"],
                        )
                        self._stop_mgr.untrack_position(
                            stop["symbol"], stop.get("strategy_name", "unknown")
                        )
                        continue
                except Exception:
                    pass  # If state read fails, proceed with stop order (safe default)

                result = self._engine.submit_order(
                    symbol=stop["symbol"],
                    side=stop["side"],
                    order_type="market",
                    qty=stop["qty"],
                    market_prices=market_prices,
                )
                with self._lock:
                    self._stats["stops_triggered"] += 1
                logger.warning(
                    "STOP ORDER SUBMITTED: %s %s %.6f — %s / 止损单已提交",
                    stop["symbol"], stop["side"], stop["qty"], stop["reason"],
                )

                # ── Sync stop-loss to Demo (prevent ghost positions) ──
                # 止損同步到 Demo（防止幽靈倉位）
                if self._demo_connector and self._demo_connector.is_enabled:
                    try:
                        _demo_stop_qty = stop["qty"]
                        if _demo_stop_qty >= 1.0:
                            _demo_stop_qty = round(_demo_stop_qty)
                        else:
                            _demo_stop_qty = round(_demo_stop_qty, 3)
                        if _demo_stop_qty > 0:
                            demo_stop_result = self._demo_connector.submit_order(
                                symbol=stop["symbol"],
                                side=stop["side"],
                                order_type="Market",
                                qty=_demo_stop_qty,
                                reduce_only=True,
                            )
                            if demo_stop_result.get("retCode") == 0:
                                logger.info(
                                    "Demo stop-loss synced: %s %s qty=%.6f / Demo 止損已同步",
                                    stop["symbol"], stop["side"], _demo_stop_qty,
                                )
                            else:
                                logger.warning(
                                    "Demo stop-loss FAILED: %s reason=%s / Demo 止損失敗",
                                    stop["symbol"], demo_stop_result.get("retMsg"),
                                )
                    except Exception as _demo_stop_err:
                        logger.warning(
                            "Demo stop-loss error: %s %s (non-fatal) / Demo 止損異常",
                            stop["symbol"], _demo_stop_err,
                        )

                if self._telegram:
                    self._telegram.alert_stop(stop["symbol"], stop["stop_type"], stop["reason"])

                # ── FA-7 / Sprint 1a P1-1: Inject into Perception Plane via _emit_round_trip ──
                # Principle 12 (Continuous Evolution): every closed position — including
                # stop-loss exits — must reach the learning pipeline so the system can
                # learn from losses and improve strategy selection over time.
                # 原則 12（持續進化）：每個被止損平倉的倉位都必須進入學習管線，
                # 系統才能從虧損中學習並持續改進策略選擇。
                #
                # P1-1 Guard: only emit round_trip if the stop order was actually executed
                # (not rejected). A rejected order means no position was closed — emitting
                # a round_trip would inject a fabricated learning signal and corrupt the
                # learning pipeline with ghost trades.
                # P1-1 守衛：只有止損單真正成交才注入學習信號；若訂單被拒（rejected_reason
                # 存在），跳過 _emit_round_trip()，避免向學習管線注入虛假數據（幽靈交易）。
                #
                # _emit_round_trip() handles:
                #   1. _open_positions pop (position metadata cleanup)
                #   2. E1 observation_writer callback
                #   3. G1 auto_deployer.on_trade_result (consecutive-loss tracking)
                #   4. L1.01 trade attribution
                #   5. EX-05 learning tier auto-promotion check
                #   6. MessageBus ROUND_TRIP_COMPLETE → AnalystAgent
                #   7. PerceptionPlane.register_data() — feeds Layer 2 AI reasoning
                # _emit_round_trip() 一次性觸發 7 個學習/歸因回調，統一複用意圖路徑的邏輯。
                #
                # Safety fallback: if result is not a dict (e.g. None), isinstance() returns
                # False → _stop_order_rejected = False → we still attempt to emit.
                # This is the safe default: a non-dict result means we cannot confirm
                # rejection, so we treat it as executed to avoid dropping valid learning data.
                # 安全 fallback：若 result 非 dict（例如 None），無法確認拒絕，
                # 預設為已成交（不丟棄潛在有效學習數據）。
                _stop_order_rejected = isinstance(result, dict) and bool(
                    result.get("rejected_reason")
                )
                if not _stop_order_rejected:
                    # Only emit round_trip when the stop order was actually executed.
                    # 只有止損單真正成交時才注入學習信號。
                    try:
                        _stop_symbol = stop["symbol"]
                        _stop_strategy = stop.get("strategy_name", "unknown")
                        # exit_price: use current_price from StopManager (exact trigger price);
                        # fall back to latest_prices snapshot if field is missing.
                        # 出場價格：優先用 StopManager 記錄的觸發價，否則取最新行情快照。
                        _exit_price = float(
                            stop.get("current_price")
                            or market_prices.get(_stop_symbol, 0.0)
                        )
                        _entry_price = float(stop.get("entry_price", 0.0))
                        _qty = float(stop.get("qty", 0.0))
                        # stop["side"] is the CLOSE-side order direction:
                        #   "Sell" means the original position was long → pnl = (exit - entry) * qty
                        #   "Buy"  means the original position was short → pnl = (entry - exit) * qty
                        # stop["side"] 是平倉方向：Sell=多頭平倉（虧則為負），Buy=空頭平倉。
                        if stop["side"] == "Sell":
                            _close_pnl = (_exit_price - _entry_price) * _qty
                        else:
                            _close_pnl = (_entry_price - _exit_price) * _qty
                        # U-05: Extract close fee from stop order fill for round-trip cost.
                        # U-05：从止损单成交记录提取平仓费用。
                        _stop_close_fee = 0.0
                        if isinstance(result, dict):
                            _stop_fills = result.get("fills", [])
                            if _stop_fills:
                                _stop_close_fee = float(_stop_fills[0].get("fee", 0.0))
                        self._emit_round_trip(
                            symbol=_stop_symbol,
                            strategy_name=_stop_strategy,
                            exit_price=_exit_price,
                            close_pnl=_close_pnl,
                            close_fee=_stop_close_fee,
                        )
                    except Exception as _rt_err:
                        # Non-fatal: do not let learning pipeline injection block stop processing.
                        # 非致命：不允許學習管線注入阻擋止損單的正常流程。
                        logger.warning(
                            "Stop-loss round-trip emit error (non-fatal): %s %s / 止損 round-trip 觸發失敗",
                            stop.get("symbol"), _rt_err,
                        )

            except Exception:
                logger.exception("Stop order submit failed / 止损单提交失败: %s", stop)

    def _invoke_scout_scan(self, symbol: str, price: float) -> None:
        """T2.07 Plan A2: Scout local market scan — volume anomaly + funding rate spike detection.
        Scout 本地市场扫描 — 成交量异常 + 资金费率尖峰检测。
        """
        try:
            if not self._scout_agent or self._scout_agent.state.value != "running":
                return

            # --- Volume anomaly check ---
            try:
                vol_data = self._km.get_volume_profile(symbol) if hasattr(self._km, 'get_volume_profile') else None
                if vol_data and isinstance(vol_data, dict):
                    vol_ratio = vol_data.get("volume_ratio", 1.0)
                    if vol_ratio > 2.0:  # 2x average volume = anomaly
                        self._scout_agent.produce_intel(
                            source=f"local_volume_scan:{symbol}",
                            content=f"Volume anomaly detected: {vol_ratio:.1f}x average for {symbol}",
                            symbols=[symbol],
                            data_quality=DataQualityLevel.FACT,
                            sentiment=SentimentScore.NEUTRAL,
                            relevance_score=min(0.9, vol_ratio / 5.0),
                            metadata={"volume_ratio": vol_ratio, "price": price},
                        )
            except Exception:
                pass  # Volume check is non-fatal

            # --- Funding rate spike check ---
            try:
                if hasattr(self._km, 'get_latest_funding_rate'):
                    fr = self._km.get_latest_funding_rate(symbol)
                    if fr is not None and abs(fr) > 0.01:  # >1% funding = spike
                        severity = "high" if abs(fr) > 0.03 else "medium"
                        self._scout_agent.produce_event_alert(
                            event_type="funding_rate_spike",
                            severity=severity,
                            affected_symbols=[symbol],
                            description=f"Funding rate spike: {fr*100:.2f}% for {symbol}",
                            metadata={"funding_rate": fr, "price": price},
                        )
            except Exception:
                pass  # Funding check is non-fatal

            self._scout_agent.record_scan()

        except Exception:
            logger.exception("Scout local scan error (non-fatal) / Scout 本地扫描异常（非致命）")

    def _try_l2_cron_trigger(self, now_ts: float) -> None:
        """
        Weekly schedule:
          Wednesday UTC 0:00 — brief report via 27B Ollama (AnalystAgent.analyze_patterns)
          Sunday    UTC 0:00 — detailed report via Claude L2 (Layer2Engine.run_session)
        每周计划：
          周三 UTC 0:00 — 简报（27B Ollama，AnalystAgent 模式发现）
          周日 UTC 0:00 — 详报（Claude L2 完整推理 session）
        """
        import asyncio
        import datetime
        try:
            utc_now = datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc)
            weekday = utc_now.weekday()  # 2=Wednesday, 6=Sunday
            week_key = utc_now.strftime("%Y-W%W")

            # ── Wednesday UTC 0:xx : brief report (27B Ollama) ──────────────
            if weekday == 2 and utc_now.hour == 0:
                brief_key = "brief_" + week_key
                if getattr(self, "_last_l2_brief_week", None) != brief_key:
                    self._last_l2_brief_week = brief_key
                    logger.info("L2 Cron: Wednesday brief report triggered (27B Ollama) / 周三简报触发")
                    insight = self._analyst_agent.analyze_patterns(force=True)
                    if insight:
                        logger.info(
                            "Wednesday brief: %d winning, %d losing patterns / 周三简报: %d 获胜模式, %d 亏损模式",
                            len(insight.winning_patterns), len(insight.losing_patterns),
                            len(insight.winning_patterns), len(insight.losing_patterns),
                        )

            # ── Sunday UTC 0:xx : detailed report (Claude L2 session) ────────
            elif weekday == 6 and utc_now.hour == 0:
                detail_key = "detail_" + week_key
                if getattr(self, "_last_l2_detail_week", None) != detail_key:
                    self._last_l2_detail_week = detail_key
                    logger.info("L2 Cron: Sunday detailed report triggered (Claude L2) / 周日详报触发")
                    try:
                        from .layer2_routes import _get_engine
                        engine = _get_engine()
                        if not engine.is_running:
                            coro = engine.run_session(
                                trigger="weekly_cron_sunday",
                                symbol="BTCUSDT",
                                context="Weekly scheduled deep analysis. Analyze all accumulated patterns, regime transitions, and strategy performance. Generate actionable insights.",
                            )
                            asyncio.ensure_future(coro)
                            logger.info("Sunday detailed L2 session scheduled / 周日详报 L2 session 已调度")
                        else:
                            logger.info("Sunday L2 skipped: another session already running / 周日详报跳过：另一 session 运行中")
                    except Exception as _e:
                        logger.warning("Sunday L2 session schedule failed (non-fatal): %s / 周日详报调度失败（非致命）: %s", _e, _e)

        except Exception:
            logger.exception("L2 Cron trigger error (non-fatal) / L2 Cron 触发异常（非致命）")

    def _check_edge_filter(self, intent: Any, market_prices: dict[str, float]) -> bool:
        """
        L1 pre-trade edge filter: ask Qwen if the signal has enough edge to trade.
        L1 交易前 edge 过滤器：询问 Qwen 当前信号是否有足够的交易优势。

        Returns True if intent should proceed, False if it should be rejected.
        返回 True 表示允许交易，False 表示拒绝。

        Design principle: fail-OPEN (if Ollama is unavailable or errors, allow the trade).
        设计原则：失败时放行（Ollama 不可用或出错时允许交易通过）。
        This is conservative in a different sense — we don't want the edge filter
        to become a single point of failure that blocks all trading.
        """
        with self._lock:
            self._edge_filter_stats["checked"] += 1

        try:
            if not self._ollama_client.is_available():
                logger.debug("Edge filter: Ollama unavailable, passing through / Ollama 不可用，放行")
                with self._lock:
                    self._edge_filter_stats["errors"] += 1
                return True  # fail-open

            # Build market context for Qwen / 为 Qwen 构建市场上下文
            symbol = intent.symbol
            side = intent.side
            price = market_prices.get(symbol, 0.0)
            strategy = intent.metadata.get("strategy_name", "unknown") if intent.metadata else "unknown"
            confidence = getattr(intent, "confidence", None) or (
                intent.metadata.get("confidence", "N/A") if intent.metadata else "N/A"
            )

            # Gather additional context from KlineManager if available
            regime_info = ""
            try:
                if hasattr(self._km, 'get_regime'):
                    regime = self._km.get_regime(symbol)
                    if regime:
                        regime_info = f"\nMarket regime: {regime}"
            except Exception as e:
                # Non-fatal: regime is optional AI context enrichment; log for observability
                # 非致命：regime 是可选 AI 上下文富化字段；记录日志以备观测
                logger.debug("Regime fetch failed for %s (non-fatal, skipping enrichment): %s", symbol, e)

            indicator_info = ""
            try:
                if hasattr(self._km, 'get_latest_indicators'):
                    indicators = self._km.get_latest_indicators(symbol)
                    if indicators and isinstance(indicators, dict):
                        # Only include key indicators
                        keys = ["rsi_14", "atr_14", "bb_width", "macd_histogram", "volume_ratio"]
                        parts = [f"{k}={indicators[k]:.4f}" for k in keys if k in indicators]
                        if parts:
                            indicator_info = f"\nIndicators: {', '.join(parts)}"
            except Exception as e:
                # Non-fatal: indicators are optional AI context enrichment; log for observability
                # 非致命：指标是可选 AI 上下文富化字段；记录日志以备观测
                logger.debug("Indicators fetch failed for %s (non-fatal, skipping enrichment): %s", symbol, e)

            context = (
                f"Symbol: {symbol}\n"
                f"Signal: {side} (strategy: {strategy}, confidence: {confidence})\n"
                f"Current price: {price:.4f}\n"
                f"Fee drag: ~0.11% round-trip (taker both sides)"
                f"{regime_info}"
                f"{indicator_info}"
            )

            resp = self._ollama_client.judge_edge(context, timeout=15)

            if not resp.success:
                logger.warning(
                    "Edge filter: Qwen error (%s), passing through / Qwen 出错，放行: %s",
                    resp.error, symbol,
                )
                with self._lock:
                    self._edge_filter_stats["errors"] += 1
                return True  # fail-open

            # Parse response / 解析响应
            # E5 NEW-S4: Use module-level _json_mod alias (consistency fix)
            # E5 NEW-S4：使用模塊級 _json_mod 別名（一致性修復）
            try:
                result = _json_mod.loads(resp.text)
                has_edge = result.get("has_edge", True)  # default: allow
                edge_confidence = result.get("confidence", 0.5)
                edge_reason = result.get("reason", "")
            except (_json_mod.JSONDecodeError, AttributeError):
                # If Qwen returns non-JSON, try heuristic
                text_lower = resp.text.lower()
                has_edge = "true" in text_lower or "yes" in text_lower
                edge_confidence = 0.5
                edge_reason = resp.text[:200]

            logger.info(
                "Edge filter: %s %s has_edge=%s confidence=%.2f reason=%s latency=%.0fms / "
                "edge 过滤: %s %s has_edge=%s",
                symbol, side, has_edge, edge_confidence, edge_reason[:80], resp.latency_ms,
                symbol, side, has_edge,
            )

            if has_edge:
                with self._lock:
                    self._edge_filter_stats["passed"] += 1
                return True
            else:
                with self._lock:
                    self._edge_filter_stats["rejected"] += 1
                return False

        except Exception as e:
            logger.warning("Edge filter exception (fail-open): %s / edge 过滤异常（放行）: %s", e, intent.symbol)
            with self._lock:
                self._edge_filter_stats["errors"] += 1
            return True  # fail-open — never block trading due to filter errors
