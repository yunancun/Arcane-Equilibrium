# Sealed Horizon Learning Plan Bridge

結論：已把 `ma_crossover|BTCUSDT|Sell` 的 240m sealed replay 候選接入 demo-learning plan / ledger / outcome horizon 路徑。它現在不會再只停在離線 replay；後續 learning lane 可以把被 Cost Gate 擋掉的真實 demo 信號按 240m horizon 累積 blocked-signal outcome。

保持邊界：

- 不降低 Cost Gate
- 不授權 probe/order
- 不下單
- 不改 env/risk/auth/strategy
- 不 deploy/restart
- 不寫 PG/schema
- 不調 Bybit private/signed/trading API

已驗證：

- focused learning-lane pytest：`70 passed`
- related alpha/profitability/learning pytest：`121 passed`
- py_compile / diff-check passed
- 用當前 Linux runtime artifact 做 Mac 本地 smoke，top candidate 為 `ma_crossover|BTCUSDT|Sell`，horizon `240`，avg net `31.8707 bps`，sample `13819`，failed gates `[]`

剩餘 blocker：runtime learning lane 仍是 `NOT_ACCUMULATING`。下一步必須讓 writer/cron/ledger/outcome rows 實際開始累積；這才會回答「被擋掉的信號是否在真實市場發展後確實可盈利」。
