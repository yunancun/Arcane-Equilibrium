---
name: Mac=開發 / Linux=Runtime 分工
description: Mac 只做開發（讀碼/寫碼/RCA/設計）；engine/python/postgres 全跑 Linux；Mac 上 engine not_running 是預期不是異常
type: project
originSessionId: aaf4cf28-cfa5-48d0-9847-f0c087dbeed8
---
# 開發環境分工（2026-04-21 確認）

- **Mac（當前 `/Users/ncyu/Projects/TradeBot/srv`）** = 開發環境。只做讀碼、寫碼、RCA、設計、測試撰寫。
- **Linux 機器** = 唯一 runtime。engine（Rust binary）、Python uvicorn、PostgreSQL、watchdog 全部只在 Linux 跑。
- 最近 commits（`c78eada` 起）在推「Mac dev-only mode」明確這個分工。

**Why**：硬件（Linux 機器是 128GB 統一記憶體目標主機）+ 部署現況；未來 Apple Silicon Mac 部署是長期目標，但當下 runtime 還在 Linux。

**How to apply**:
- 在 Mac 接手時**跳過「engine 存活」檢查**，`pipeline_snapshot.json` 不存在 / watchdog status = not_running 都是正常。
- 「接手三連」在 Mac 上只做：git 狀態 + TODO.md 第一個 `[ ]` + `docs/worklogs/` 最新設計日誌。
- 需要查 runtime 狀態（DB 行數、fills 累積、engine log）→ 透過 Tailscale 或 ssh 連 Linux，不在 Mac 本地查。
- 需要跑 `restart_all.sh --rebuild` / `python` engine / `psql` → 都在 Linux 上；Mac 上**不要嘗試啟動 engine**。
- Mac 上能直接做的：Rust/Python 代碼編輯、`cargo check`（不 run）、單元測試（不依賴 DB/socket 的）、設計文檔、RCA。
