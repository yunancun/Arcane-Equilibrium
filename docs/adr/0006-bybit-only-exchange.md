---
status: accepted
date: 2026-04-03
---

# Bybit is the sole exchange; multi-exchange support is descoped

> ⚠️ **AMENDED（记于 2026-07-18 文档审计）**：核心结论「Bybit 是当前唯一 live 执行所」仍成立，但「Binance 仅作假设性长期选项 / 多所 descoped」的框架已被后续决定修订——ADR-0033（Binance market-data 接入）、ADR-0040（multi-venue gate spec）、ADR-0048 + AMD-2026-07-11-01（IBKR `stock_etf_cash` lane 开发授权，仍未激活）。当前 venue 权威见 `CLAUDE.md` §一。

Early planning included Binance as a second venue; on 2026-04-03 the project officially focused all execution, connectors, and policy work on Bybit only. Binance is retained only as a hypothetical long-term option.

## Consequences

We can write Bybit-specific REST/WS/IPC integration directly, maintain a single API reference (`docs/references/2026-04-04--bybit_api_reference.md`), and run a `BB` agent (Bybit Broker Compatibility Auditor) that pushes back from Bybit's compliance/policy perspective on any Bybit-violating design. New Venue Adapter abstractions should not over-generalize; YAGNI applies until a second venue is reopened.
