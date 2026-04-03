# Canary Validation Tools (R-07)

Tools for the R-07 canary validation phase of the Rust migration.

## Components

| File | Purpose |
|------|---------|
| `canary_schema.py` | JSONL record schema + builder + validator |
| `canary_comparator.py` | Compare Rust vs Python JSONL outputs |
| `engine_watchdog.py` | Monitor Rust engine health, trigger fallback on crash |
| `rollback_drill.sh` | Rollback rehearsal script (< 10 min SLA) |

## Usage Flow

1. Rust engine writes `engine_results.jsonl` (one line per tick)
2. Python shadow writes `shadow_results.jsonl` (matching schema)
3. `canary_comparator.py` joins on (timestamp, symbol), applies tolerance tiers
4. Daily report generated to `trading_services/canary_reports/`
5. 7 consecutive days with 0 CRITICAL + <10 WARNING = PASS

## Tolerance Tiers (from V3-FINAL)

| Category | Tolerance | Examples |
|----------|-----------|---------|
| Simple aggregates | 1e-10 | SMA, EMA, balance |
| Recursive indicators | 1e-8 | RSI, MACD, Stochastic |
| Hurst/complex | 1e-6 | Hurst exponent |
| Signal direction | Strict | With boundary exemption (value within 0.5% of threshold) |
| H0 Gate / SM | Strict | Exact match required |
