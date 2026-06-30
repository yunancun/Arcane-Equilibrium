# Operator Brief - IBKR Stock/ETF Rust IPC Request Contract Test Split Guard

日期：2026-06-30
結論：完成一個 source-only / behavior-preserving Rust IPC test structure checkpoint。

## 做了什麼

- 把 Stock/ETF Rust IPC 父測試檔中的 paper/fill/shadow/readonly-probe request
  contract tests 拆到 `request_contracts.rs`。
- 父檔 `stock_etf.rs` 從 `1852` 行降到 `1110` 行。
- 新子檔 `request_contracts.rs` 為 `745` 行；既有 `status_fixtures.rs` 為
  `685` 行。
- Structure guard 現在要求 Rust IPC test 父/子檔都低於 `1200` 行。
- Guard 也防止 moved fixture 檔引入 IBKR SDK 或 socket/HTTP client token。

## 驗證

- `rustfmt`：PASS
- Engine `stock_etf` filter：`31 passed`
- Rust IPC test split static guard：`3 passed`
- Full Stock/ETF FastAPI/static：`105 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

## 不代表什麼

不代表新增 IPC method、不代表 IBKR 已接通、不代表 Phase 2/3 啟動、不代表 secret
slot 建立、不代表 connector runtime、read probe execution、paper order、fill import、
evidence writer、DB apply 或 live/tiny-live 權限。Bybit live 行為未變。
