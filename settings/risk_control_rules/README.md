# risk_control_rules
# risk_control_rules

这里存放风控规则和交易保护规则。
This folder stores risk control rules and trading protection rules.

这些规则用于限制风险、保护资金并防止系统在异常条件下继续交易。
These rules are used to limit risk, protect capital, and prevent the system from continuing to trade under abnormal conditions.

`risk_config_stock_etf_paper.toml` is the dormant ADR-0048 Stock/ETF cash
paper/shadow risk config. It is source-validated by
`stock_etf_risk_policy_v1`; it is not wired into the Bybit runtime hot path and
does not authorize IBKR contact, connector runtime, paper orders, scorecards,
tiny-live, or live.
