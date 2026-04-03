# Phase R-01：IPC + shared_types + WebSocket（Week 1-2）

**週期**：Rust 主開發 Week 1-2
**工時**：~2 週
**前置**：`00--preparation_parallel.md` 全部 Go + Phase 3 結束（L2 凍結）
**下一階段**：`02--core_upper.md`

---

## 上下文導航

```
源文件：V3-FINAL §4（IPC 協議）+ §3（依賴斷裂修復）
前置完成狀態：openclaw_types 已編譯 · CI 綠色 · L1+L2 接口凍結
本階段目標：建立 Rust↔Python 通信管道 + Python 側斷裂修復基礎設施
```

---

## 具體任務

### Rust 側

### [ ] R01-1：engine/ipc_server.rs — Unix domain socket JSON-RPC 2.0 服務端
- socket 路徑 `/run/openclaw/engine.sock` [V3-PA-4]
- RuntimeDirectory=openclaw 在 systemd 中配置
- 啟動時檢查並重建 socket（防 tmpwatch 清理）
- **~400 行**

### [ ] R01-2：engine/main.rs 骨架 — tokio runtime + 信號處理
- `runtime::Builder::new_current_thread` 用於 tick actor [V3-E5-4]
- 獨立 multi_thread runtime 用於 IPC/後台任務
- SIGHUP handler → reload config [V3-PA-5]
- **~300 行**

### [ ] R01-3：engine/ws_client.rs — Bybit WS 連接 + 自動重連
- tokio-tungstenite 實現
- JSON 解析 → PriceEvent → 推送到 tick actor 的 mpsc channel
- 心跳 + 自動重連 + exponential backoff
- **~300 行**

### [ ] R01-4：engine/config.rs — ArcSwap\<Config\> 熱加載 [V3-E5-6]
- 從 engine.toml 讀取
- 分冷/熱參數 [V3-PA-5]
- SIGHUP → 重讀 toml → ArcSwap store
- **~200 行**

### Python 側

### [ ] R01-5：app/shared_types.py — 枚舉/dataclass 共享層
- 4 enum（RiskLevel/RiskInitiator/OrderState/OrderInitiator）
- 6 dataclass（H0GateRiskSnapshot/H0GateConfig/H0GateCheckResult/H0GateHealthSnapshot/StopConfig/PriceEvent）[V3-FA-1]
- 與 openclaw_types crate 嚴格 1:1 對齊
- **~120 行**

### [ ] R01-6：app/ipc_client.py — Python→Rust IPC 客戶端
- Unix socket JSON-RPC 2.0 客戶端
- 自動重連 + exponential backoff + 3 次失敗降級 [V3-PA-4]
- **~300 行**

### [ ] R01-7：app/ai_service.py — Rust→Python AI 請求處理
- 接收 strategist_evaluate / analyst_evaluate 等 RPC
- 轉發到對應 Agent
- 回覆結果
- **~500 行**

### [ ] R01-8：conftest.py 改造第一批 [V3-FA-4]
- PriceEvent → 從 shared_types 導入
- OrderState/OrderInitiator → 從 shared_types 導入
- SM 類 fixture → 暫用 MagicMock（W9 最終改為 IPC mock）

### [ ] R01-9：CI JSON Schema diff [V3-PA-6]
- Rust 側 serde_json 導出 schema
- Python 側 dataclasses 導出 schema
- CI 對比 → 不一致 FAIL

---

## Go/No-Go 門控

- [ ] IPC 雙端 echo ping-pong 通過
- [ ] IPC 壓測 1000 msg/s 穩定
- [ ] shared_types CI schema diff PASS
- [ ] WS 能接收 Bybit testnet 數據
- [ ] conftest 改造後現有測試不回退

---

## 與現有工作交叉

| 交叉點 | 處理 |
|--------|------|
| Phase 0 U-11 交易所條件單 | U-11 的 WS 使用不受影響（仍是 Python 側 BybitDemoConnector） |
| Phase 3 完成 | 本階段必須等 Phase 3 結束（L2 凍結）才能啟動 |

---

## 進度追蹤

| 任務 | 狀態 | 完成日期 | commit |
|------|------|---------|--------|
| R01-1 ipc_server.rs | [ ] | | |
| R01-2 main.rs | [ ] | | |
| R01-3 ws_client.rs | [ ] | | |
| R01-4 config.rs | [ ] | | |
| R01-5 shared_types.py | [ ] | | |
| R01-6 ipc_client.py | [ ] | | |
| R01-7 ai_service.py | [ ] | | |
| R01-8 conftest 改造 | [ ] | | |
| R01-9 CI schema diff | [ ] | | |

---

## 問題與變更

（空）
