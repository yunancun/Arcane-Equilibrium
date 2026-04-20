# monitoring_services

Grafana monitoring stack for OpenClaw Trading AI system.

## Components

- **Grafana** (port 3000) - Dashboard visualization, connected to PostgreSQL + FastAPI

## Quick Start

```bash
cd "${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}/docker_projects/monitoring_services"
docker compose up -d
```

## Access

- Local: http://localhost:3000
- Tailscale: http://trade-core:3000
- Login: admin / <REDACTED>

## Datasources

| Name | Type | Connection |
|------|------|------------|
| PostgreSQL | postgres | trading_postgres:5432 / trading_ai |
| TradingAPI | json-datasource | host.docker.internal:8000 (FastAPI) |

## Dashboards (5)

1. **System Overview / 系统总览** - Health status, observer verdicts, component latency, risk events, runtime state
2. **Trading PnL / 交易损益** - Net PnL trend, cost breakdown, win rate, Sharpe, trade executions, account equity
3. **AI Cost Tracking / AI 成本追踪** - Cumulative cost, budget gauge ($15/day), provider/tier/purpose breakdown, token usage, model table
4. **Positions & Orders / 持仓与订单** - Open positions, order flow, execution history, order type/status distribution, fees
5. **Market Data & Risk / 行情与风控** - Price tracking, funding rates, open interest, bid-ask spread, risk events, learning pipeline

## Database Schema

Tables created in `trading_ai` database (see `init_trading_schema.sql`):

- `account_snapshots` - Account equity/balance over time
- `position_snapshots` - Position tracking
- `order_events` - Order lifecycle events
- `trade_executions` - Fill/execution records
- `ai_cost_events` - AI API cost tracking (H5/Layer 2)
- `system_health` - Component health snapshots
- `observer_verdicts` - Decision packet verdicts
- `paper_pnl_snapshots` - Paper trading PnL snapshots
- `risk_events` - Risk framework events (P0/P1/P2)
- `market_tickers` - Market data snapshots
- `learning_events` - Learning pipeline events

## Re-initialize Schema

```bash
docker exec -i trading_postgres psql -U trading_admin -d trading_ai < init_trading_schema.sql
```
