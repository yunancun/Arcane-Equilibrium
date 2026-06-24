# Operator Note -- Profit Evidence Cleanup And Candidate Selection

STATUS: DONE_WITH_CONCERNS

本輪已按你的 Demo API 授權執行一次 Demo-only 風險清理，並完成 exactly-one
bounded Demo candidate review packet。

## 已執行

- 走 control API：`POST /api/v1/strategy/demo/session/stop`
- 使用 Bearer token + CSRF double-submit；未打印 token。
- E3/BB 均 PASS 此路徑；direct Bybit REST 被拒絕作為本輪路徑。
- 結果：
  - `cancel_orders`: found `20`, cancelled `35`
  - `orphan_sweep`: found `1`, swept `1`
  - `verify.clean=true`
  - cleanup 後 Demo open orders `0`
  - cleanup 後 Demo open positions `0`

## 不能當盈利證據

- PG 仍有 `874` 筆 demo `Working` stale rows，需要 quarantine。
- SOL/ETH entry fills 仍有 unattributed lineage。
- cleanup close fill 只是風險降低證據，不是 bounded-probe proof、Cost Gate proof、
  promotion proof，也不是可信 risk-adjusted net PnL proof。

## 本輪唯一候選

- `grid_trading|AVAXUSDT|Sell`
- 60m horizon
- 48/48 net-positive blocked outcomes
- avg net `73.5511bps` after 4.0bp cost
- wrongful-block score `147.1021`

Authority 仍全關：

- no global Cost Gate lowering
- no probe authority
- no order authority
- no promotion evidence
- no live/mainnet

## 下一步

下一閘是 `P0-BOUNDED-PROBE-AUTHORIZATION`。即使你已授權 Demo API，本候選仍需要
candidate-specific bounded-probe authorization packet：side-cell、order budget、expiry、
proof exclusions、matched controls、fee/slippage and execution-realism review 都要明確。
