# 已完成 TODO 歸檔：Live GUI P0~P6 + DEAD-PY-1/2 + 1C-4

**歸檔日期**：2026-04-10
**來源**：`TODO.md` Section 0、Section 2、Section 3、Section 4
**全部 commit 完成，已移出主 TODO.md。**

---

## Section 0：Live GUI + Per-Engine Risk + API Key 管理（DONE 2026-04-10）

目標：Live 頁面功能完備可測試、風控按引擎分離、GUI 可安全填入/替換 API key。
物理隔離原則：Live key 槽（`secrets/secret_files/bybit/live/`）目前填另一個 Demo 帳號，上線時換 key，零代碼改動。

### P0 — GUI 框架 + API key 管理

- [x] **LIVE-P0-1** `tab-settings.html` API Key 管理區塊 ✅ (commit c680ffd)
- [x] **LIVE-P0-2** `tab-live.html` 前置條件動態化 ✅ (commit c680ffd)
- [x] **LIVE-P0-3** `tab-live.html` 實盤儀表板框架 ✅ (commit c680ffd)

### P1 — Rust TradingMode::Live + 槽位感知 key 讀取

- [x] **LIVE-P1-1** `read_secret_file(slot)` 槽位感知 ✅ (commit 11283c7)
- [x] **LIVE-P1-2** `TradingMode::Live` variant ✅ (commit 11283c7)
- [x] **LIVE-P1-3** `/api/v1/live/session/start|stop|status` 路由 ✅ (commit 11283c7)

### P2 — Per-Engine RiskConfig 分離

- [x] **LIVE-P2-1** 三個獨立 RiskConfig 文件（paper/demo/live）✅ (commit 006d905)
- [x] **LIVE-P2-2** GUI per-engine tab + Live 二次確認彈窗 ✅ (commit 006d905)
- [x] **LIVE-P2-3** E2 + E4 全量回歸 ✅ (commit 006d905)

### P3 — Gov-P1 + 全阻隔移除 + 縮倉監控（2026-04-10）

- [x] **LIVE-P3-1** `post_live_session_start` 自動授予 `execution_authority` ✅ (commit 045e79c)
- [x] **LIVE-P3-2** 移除 `OPENCLAW_ALLOW_MAINNET=1` Rust hard guard ✅ (commit 25b5d73)
- [x] **LIVE-P3-3** `_live_contraction_monitor()` 5%/15% 縮倉監控 ✅ (commit 25b5d73)

### P4 — Live-Demo 槽位 + 指標端點（2026-04-10）

- [x] **LIVE-P4-1** `live_demo` 虛擬槽位 + 3 API key 卡片 ✅ (commit 25b5d73)
- [x] **LIVE-P4-2** `/api/v1/live/metrics` + paper `/metrics` 修復 ✅ (commit 25b5d73)

### P5 — Live GUI 紫色主題 + 擴展儀表板（2026-04-10）

- [x] `live_reserved` 所有紅色 → 紫色主題 ✅ (commit c392220)
- [x] Account Balance 卡片組（equity/available/wallet/margin-used）✅
- [x] PnL Overview（unrealized + realized + net）✅
- [x] 持倉表 + Leverage 列 + 成交記錄懶加載 ✅
- [x] Global Mode Gate（409 block if not live_reserved）✅

### P6 — Live-Demo 虛擬 key + 更多指標（2026-04-10）

- [x] 10 個 Performance Metrics 卡（30s 自動刷新）✅ (commit 25b5d73)

### 補充完成項

- [x] **SM-1 live 授權統一**：`max_position_usd` 從 Rust RiskConfig 讀取 + live session SM-1 生命週期 ✅ (commit 435e613)
- [x] **Live/Demo 平倉按鈕**：單倉 + 全部平倉 + `_normalize_execution()` Rust 映射 ✅ (commits c370cd1/bfc3cea/81a0acb)
- [x] **Signal Diamond Phase 1-4 + Fix Round**：per-mode state swap + IPC AddMode/SwitchMode 全鏈路 ✅
- [x] **SEC-05 innerHTML XSS**：`ocEsc()` 全量包裹 ✅ (commit af392c2)
- [x] **Live_Ready 宣告**：所有代碼阻隔移除，僅差 API key ✅

---

## Section 2：ARCH-RC1 1C-4 最終收尾（DONE）

- [x] **A2** NewsPipeline 60s scheduler spawn ✅
- [x] **1C-4 最終驗收** E2 + E4 + QA Audit + 文檔同步 ✅

---

## Section 3：DEAD-PY-1 死代碼清理（DONE）

- [x] Phase 3 殘留 state_*.py / pnl_ops.py 「Wave A/B/C」標籤移除 ✅
- [x] `main.py:176` 舊命名清理 ✅
- [x] whitelist UI 全量移除（tab-governance.html 220 行 + governance.js 19 行）✅

> KEEP（永遠不要動）：`risk_view_client.py:196-197` force_governor_tier_* / `apply_ai_consultation` / `governance_hub.py` RC-11 docstrings — 全有 test callers 或生產呼叫。

---

## Section 4：DEAD-PY-2 大型死代碼清理（DONE 2026-04-10 · commit f3d0ff7）

**結果**：~4500 行刪除。41 files changed, 339 ins, 16011 del。Python 層完全無交易邏輯。

- [x] Phase A：4 bridge 文件全刪（bridge_core/agents/stats/pipeline_bridge）✅
- [x] Phase B：5 Python 策略類全刪（ma_crossover/bollinger_reversion/funding_rate_arb/grid_trading/bb_breakout）✅
- [x] Phase C：ProtectiveOrderManager 全刪 ✅
- [x] Phase D：BybitDemoConnector 交易方法全刪（保留 2 個工具函數）✅
- [x] Phase E：11 死 test 文件 + 10+ 文件外科手術刪 dead class + strategy_wiring 瘦身 ✅
- [x] E4 回歸：872 Rust lib + 2427 Python passed (1 pre-existing fail) ✅
