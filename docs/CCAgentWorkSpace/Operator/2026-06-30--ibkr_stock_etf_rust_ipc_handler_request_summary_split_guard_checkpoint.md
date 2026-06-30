# Operator Brief - IBKR Stock/ETF Rust IPC Handler Request Summary Split Guard

日期：2026-06-30
結論：完成一個 source-only / behavior-preserving Rust IPC production handler structure checkpoint。

## 做了什麼

- 把 Stock/ETF Rust IPC handler 裡的 request parsing 與 paper/fill/shadow/readonly-probe
  summary helpers 拆到 `request_summaries.rs`。
- 父檔 `stock_etf.rs` 從 `1292` 行降到 `823` 行。
- 新子檔 `request_summaries.rs` 為 `477` 行；既有 `status_summaries.rs` 為
  `934` 行。
- Structure guard 現在要求 handler 父/子檔都低於 `1200` 行，且子模組集合固定。
- Guard 也防止 moved helper 檔引入 IBKR SDK 或 socket/HTTP client token。

## 驗證

- `rustfmt --check`：PASS
- Engine `stock_etf` filter：`31 passed`
- Rust IPC handler/test split static guards：`6 passed`
- Full Stock/ETF FastAPI/static：`105 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

## 不代表什麼

不代表新增 endpoint、不代表新增 IPC method、不代表新增 dispatch route、不代表 IBKR
已接通、不代表 Phase 2/3 啟動、不代表 secret slot 建立、不代表 connector runtime、
read probe execution、paper order、fill import、evidence writer、DB apply 或
live/tiny-live 權限。Bybit live 行為未變。
