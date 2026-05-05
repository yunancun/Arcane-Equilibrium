---
status: accepted
date: 2026-04-03
---

# Bybit is the sole exchange; multi-exchange support is descoped

Early planning included Binance as a second venue; on 2026-04-03 the project officially focused all execution, connectors, and policy work on Bybit only. Binance is retained only as a hypothetical long-term option.

## Consequences

We can write Bybit-specific REST/WS/IPC integration directly, maintain a single API reference (`docs/references/2026-04-04--bybit_api_reference.md`), and run a `BB` agent (Bybit Broker Compatibility Auditor) that pushes back from Bybit's compliance/policy perspective on any Bybit-violating design. New Venue Adapter abstractions should not over-generalize; YAGNI applies until a second venue is reopened.
