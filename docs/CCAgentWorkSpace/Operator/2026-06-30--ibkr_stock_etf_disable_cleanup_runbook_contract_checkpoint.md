# Operator 摘要 — IBKR Stock/ETF Disable-Cleanup Runbook Contract

日期：2026-06-30
範圍：IBKR `stock_etf_cash` paper/shadow lane source-only checkpoint

## 結論

已新增 `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` source validator。

這讓未來 IBKR Stock/ETF paper/shadow lane 的「關閉 / disable / cleanup」證據
可以被 machine-check，而不是只靠文字 runbook。

## 現在能檢查什麼

- stock/ETF lane flag 關閉
- IBKR read-only / paper flag 關閉
- shadow-only posture 保留
- collector 已停止
- GUI 股票視圖 disabled 或 hidden
- live secret absence proof
- evidence archive forward-only
- DB retention forward-only，不 destructive cleanup
- append-only audit preserved
- Bybit live execution unchanged

## 仍然不授權

- 不接觸 IBKR
- 不建立 secret slot
- 不啟動 connector
- 不送 paper order
- 不刪 DB / truncate DB
- 不開始 evidence clock
- 不授權 release
- 不授權 GUI lane selection
- 不授權 tiny-live / live

第一個 IBKR contact 仍需要 real secret/topology evidence + immutable Phase 2 PASS artifact。
