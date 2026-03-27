# =============================================================================
# Trading Strategies Package / 交易策略包
# =============================================================================
#
# MODULE_NOTE (中文):
#   具体交易策略实现：Funding Rate 套利、Bollinger 均值回归、Grid Trading 等。
#   每个策略独立一个文件，统一继承 StrategyBase 抽象类。
#   策略只生成交易信号，不直接提交订单（由 Strategy Orchestrator 统一管理）。
#
# MODULE_NOTE (English):
#   Concrete trading strategy implementations: Funding Rate Arbitrage,
#   Bollinger Mean Reversion, Grid Trading, etc.
#   Each strategy is a separate file, all inherit from StrategyBase ABC.
#   Strategies only generate trading signals, not submit orders directly
#   (managed by the Strategy Orchestrator).
# =============================================================================
