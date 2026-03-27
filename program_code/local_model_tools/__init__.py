# =============================================================================
# OpenClaw Phase 2: Local Trading Strategy Toolkit / 本地交易策略工具包
# =============================================================================
#
# MODULE_NOTE (中文):
#   Phase 2 本地策略工具包的根模块。
#   此包包含技术指标引擎、K线管理器、信号生成器、交易策略实现，
#   以及策略编排器。所有组件均在本地运行（零 AI 成本），
#   仅与 Paper Trading Engine 交互（不接触真实交易 API）。
#
# MODULE_NOTE (English):
#   Root module for the Phase 2 local trading strategy toolkit.
#   This package contains the technical indicator engine, kline manager,
#   signal generator, trading strategy implementations, and strategy
#   orchestrator. All components run locally (zero AI cost) and only
#   interact with the Paper Trading Engine (never touch real trading APIs).
#
# Safety invariant / 安全不变量:
#   - system_mode = read_only, execution_state = disabled (硬边界不变)
#   - 所有交易信号仅提交到 paper trading engine (is_simulated=True)
#   - All trading signals are submitted to paper trading engine only
# =============================================================================
