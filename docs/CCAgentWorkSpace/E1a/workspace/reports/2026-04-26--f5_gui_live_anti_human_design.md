# E1a · F5 GUI Live tab anti-human-design 修復

**日期**：2026-04-26 · **分支**：`e1-f5-gui-live-anti-human-design` · **commit**：`51be82f`

## 工作內容

A3 UX audit 揭發 LiveDemo 模式下 tab-live 永遠渲染紫色「Live 实盘 運行中 🟣」+ demo 帳戶數據 — 違反 CLAUDE.md §二 #8。本任務 F5 修 5 個 anti-human-design findings：

- **A1 (P0)** — Live tab 幽靈視圖 → 後端 phantom-view guard + 前端 page-load engine_kind 檢查 + 3-mode 視覺差異（Mainnet 紫紅 / LiveDemo 橙 / unconfigured 灰警示）
- **A2 (P1)** — 側欄 Net PnL 對齊 tab-live「今日淨 PnL」（unrealized + realized − fees）
- **A3 (P1)** — Live Tab 紅紫雙線 + 「⚠ REAL FUNDS」徽章常駐
- **A4 (P2)** — 寫操作按鈕 client-side guard（engine != live OR auth != granted → disable + tooltip）
- **A5 (P2)** — Fill 時間 UTC + local 雙標（替換原 `toLocaleTimeString()` 單時區）

## 修改檔案

```
program_code/exchange_connectors/bybit_connector/control_api_v1/
├── app/live_session_routes.py                +52 行 (helper + setdefault)
├── app/live_session_account_routes.py        +95 行 (phantom guard + 5 endpoint hook)
├── app/static/tab-live.html                 +378 行 (CSS + view swap + JS)
├── app/static/console.html                   +89 行 (Live tab CSS + sidebar net PnL)
└── tests/test_live_session_endpoint_actual_engine_kind.py  新增 +200 行 (11 pytest)
```

5 檔 / 892 insertions / 73 deletions

## 測試結果（SSH bridge to trade-core）

| Test 套件 | 結果 |
|----------|------|
| 新增 `test_live_session_endpoint_actual_engine_kind.py` | **11 passed** in 0.29s |
| Baseline `test_live_gate_fallback.py` + `test_paper_live_gate.py` | **72 passed** in 0.34s（不退） |

## 重要設計決策

### LiveDemo 不被當「未配置」處理（per CLAUDE.md memory）
LiveDemo 是 design intent（live 管線跑 demo endpoint，authorization/TTL/風控按 Live 嚴格標準）；只在視覺差異化（橙色 vs 紫色），不在後端 guard 擋。phantom-view guard 只擋 `engine_kind != "live" AND endpoint == "unconfigured"` 的雙重失效情境。

### 後端回 200 + structured error 而非 422
`/balance|positions|orders|fills|metrics` 在 phantom 情境回 HTTP 200 + `{error: "live_slot_not_configured", actual_engine_kind, actual_endpoint, ...}`。原因：現有 GUI `ocApi` 對 non-200 顯通用 toast，無法走 page-load 流程讀 markers swap views。改回 200 + structured envelope 讓前端結構化 short-circuit。

### Mac dev → SSH bridge 強制
Mac 沒裝 fastapi → pytest 必走 `ssh trade-core "python3 -m pytest ..."`。Mac 端只能 `python3 -m ast.parse` syntax check。

## 跨平台合規

`_resolve_live_endpoint_label()` 用 `os.environ.get("OPENCLAW_SECRETS_DIR") or str(Path.home() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit")` — 遵循 §七 ★★ 跨平台規範。

## 下一步

- ✅ 已 commit + push 至 `origin/e1-f5-gui-live-anti-human-design`
- ⏳ 待 `@E2` 代碼審查
- ⏳ 待 `@A3` UX 必審
- ⏳ 待 `@E4` GUI 靜態測試 + 手動驗證 3 mode（mainnet/live_demo/unconfigured）視覺差異

## 教訓（追加 memory）

1. **Multi-session race condition 中**：當主 srv 工作樹頻繁被別 session reset 分支（本任務嘗試前 2 次都被 reset），改用 `git worktree add` 隔離工作流是穩定方案。
2. **Mac dev syntax check**：純 Python `ast.parse` 不能驗 fastapi 邏輯，但能擋住明顯 syntax error；SSH bridge 跑 pytest 是真正驗證手段。
3. **HTML 1659 行**：靜態資源不受 §九 1200 硬上限，但接近邊界；下次再加應分拆 JS 出來成 sibling `tab-live-handlers.js`。
