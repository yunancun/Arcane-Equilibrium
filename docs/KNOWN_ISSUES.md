# Known Issues & Unverified Risks
# 已知問題與未驗證風險
#
# 用途：記錄已識別但尚未修復/驗證的問題，供每次 session 接手時排查參考。
# Purpose: Track identified but unresolved/unverified issues for troubleshooting reference.
#
# 格式：每個問題獨立章節，含 狀態/位置/排查方式/緩解方案。
# 狀態：OPEN（待驗證）/ CONFIRMED（已確認是問題）/ RESOLVED（已修復，附 commit）
#
# 統計：OPEN 11 / CONFIRMED 0 / RESOLVED 3
# 最後更新：2026-04-03

---

# ━━━ Rust Engine（R-05 Soak Test 排查項）━━━

## OPEN — RE-1：Rust Engine 長期記憶體洩漏風險

**來源**：R-05 決策（2026-04-03），10 分鐘實測無法覆蓋
**嚴重性**：HIGH
**可能位置**：
- `rust/openclaw_engine/src/paper_state.rs` — `fills: Vec<PaperFill>` 無上限，持續累積
- `rust/openclaw_engine/src/paper_state.rs` — `positions` / `latest_prices` HashMap（需確認無殭屍 key）
- `rust/openclaw_engine/src/persistence.rs` — JSONL audit 檔案持續增長（磁碟而非記憶體，但需監控）
- 策略內部窗口（MA max 200、BB max 20 — 已有上限，低風險）
**排查方式**：24h soak test 後檢查 RSS 記憶體趨勢，應持平而非線性增長
**緩解方案**：fills Vec 加 ring buffer 或定期歸檔截斷

---

## OPEN — RE-2：WS 24h 強制斷線無自動重連

**來源**：R-05 決策（2026-04-03）
**嚴重性**：HIGH
**背景**：Bybit production WS 連線超過 24 小時後強制斷線
**位置**：`rust/openclaw_engine/src/ws_client.rs` — `connect()` / event loop
**現狀**：無自動重連邏輯，斷線後 event loop 結束，程序靜默停止
**排查方式**：觀察 24h 後是否收到 WS Close/Error，程序是否 panic 或靜默退出
**緩解方案**：event loop 外層加 reconnect-with-backoff 迴圈（建議在 R-06 或 soak test 後實作）

---

## OPEN — RE-3：跨 UTC 日切邊界行為未驗證

**來源**：R-05 決策（2026-04-03）
**嚴重性**：MEDIUM
**背景**：Bybit kline 以 UTC 00:00 為日切界，日切瞬間可能出現：
- 1D kline confirm=true 收盤 candle 觸發大量策略信號
- funding rate settlement（每 8h，00:00 是其中之一）
- 瞬間 spread 擴大 / 流動性下降
**位置**：策略的 kline 消費邏輯（MA/BB 使用日線窗口時）
**排查方式**：soak test 跨越 UTC 00:00，檢查是否有異常信號爆發或 PnL 突變
**緩解**：策略已有 cooldown 機制，但日切集中信號是否超出 cooldown 設計未驗證

---

# ━━━ 架構 / 管線問題 ━━━

## OPEN — ARCH-1：MessageBus Guardian→Executor 路徑未打通

**來源**：PA 技術審查（2026-04-01）
**嚴重性**：HIGH
**問題**：Guardian 從未向 Executor 發送 APPROVED_INTENT。Conductor 有完整 `process_trade_intent()` 邏輯但生產環境從未被調用。5-Agent MessageBus 全路徑處於斷開狀態。
**位置**：`app/guardian_agent.py`（發送端）、`app/multi_agent_framework.py`（Conductor 編排）
**影響**：Agent 間的正式通信管線無法工作，所有交易意圖通過 PipelineBridge 直接處理而非經 MessageBus
**排查方式**：檢查 Guardian approve 後是否有 bus.send() 調用
**備註**：`guardian_agent.py:411` 有 TODO 標記待啟用 bus flow

---

## OPEN — ARCH-2：Pipeline Bridge GovernanceHub 注入時序風險

**來源**：PA 審查（2026-03-31）
**嚴重性**：MEDIUM
**問題**：PipelineBridge 在 `phase2_strategy_routes.py` 注入 GOV_HUB 之前就已創建，存在 `_governance_hub=None` 的時間窗口
**位置**：`app/pipeline_bridge.py` + `app/phase2_strategy_routes.py`
**影響**：時間窗口內的 intent 可能繞過治理檢查（fail-open 設計）
**緩解**：啟動順序在當前 demo 場景下是可控的，但 live 前需驗證

---

## OPEN — ARCH-3：TruthSourceRegistry + ExperimentLedger 持久化不完整

**來源**：PA 技術審查（2026-04-01）
**嚴重性**：MEDIUM
**問題**：ExperimentLedger 有 `save_snapshot()` / `load_snapshot()` 實現，但生產代碼中 `save_snapshot()` 的自動定期調用尚未確認接通。系統重啟可能丟失累積的學習數據。
**位置**：`app/experiment_ledger.py`、`app/experiment_routes.py`
**影響**：重啟後 ExperimentLedger 的假設數據可能丟失
**排查方式**：確認 `save_snapshot()` 是否在 shutdown hook 或定期任務中被調用

---

## OPEN — ARCH-4：Dependency Injection Silent Fail-Open 模式

**來源**：PA 審查（2026-03-31）
**嚴重性**：MEDIUM
**問題**：5 個核心安全組件使用 `if self._xxx:` 模式（Python None 初始化），依賴注入失敗時靜默 no-op 而非報錯
**位置**：`pipeline_bridge.py`、`guardian_agent.py`、`strategist_agent.py` 等
**影響**：如果依賴注入失敗，安全檢查靜默跳過而非 fail-closed
**緩解**：當前 demo 場景風險有限，live 前需改為顯式 fail-closed

---

# ━━━ 交易邏輯問題 ━━━

## OPEN — TRADE-1：Strategy Alpha 未經統計驗證

**來源**：改善報告 V3 Final（2026-04-03）
**嚴重性**：HIGH（業務風險，非代碼缺陷）
**問題**：所有 5 個策略使用標準 TA 指標，無統計 edge 驗證。Paper 交易 4 週顯示負淨 PnL。
**影響**：live 交易可能持續虧損
**緩解**：Alpha 基準測試並行進行中（Phase 0 Day 1 開始 2 週 Paper）

---

## OPEN — TRADE-2：Intent 排隊競態條件

**來源**：改善報告 V3 Final（2026-04-03）
**嚴重性**：MEDIUM
**問題**：Normal channel 推送 long intent + 閃崩觸發 fast-lane close_all。若 Guardian 先處理 long（approved → 開倉），再處理 close_all（平倉），雙重手續費浪費。
**位置**：`app/pipeline_bridge.py` intent 隊列 + `rust/openclaw_engine/src/fast_track.rs`
**緩解**：fast_track 有 pre-empt 設計，但 Python 側排隊順序未保證

---

## RESOLVED — TRADE-3：Kelly 計算偏差 — 未實現 PnL 未計入勝率

**來源**：改善報告 V3 Final（2026-04-03）
**嚴重性**：MEDIUM
**問題**：`win_rate` 和 `avg_win/avg_loss` 只算已平倉交易。未平倉虧損倉位被排除 → 勝率虛高 → Kelly fraction 過於激進
**位置**：`position_sizer.py` Kelly 計算
**修復**：新增 `unrealized_pnl` 參數，負值時 dampening=max(0.5, 1-|pnl|/balance)（2026-04-03）

---

## OPEN — TRADE-4：Partial Fill 回滾數量不一致

**來源**：改善報告 V3 Final（2026-04-03）
**嚴重性**：MEDIUM
**問題**：限價單部分成交（下 0.1 BTC，成交 0.06），回滾時應平 0.06 而非 0.1 → 倉位大小錯誤
**位置**：`app/paper_trading_engine.py` + `app/oms_state_machine.py`
**影響**：Paper 中影響有限，live 時可能導致超額平倉或不足平倉
**備註**：`compute_partial_fill_qty()` 已實現，但回滾路徑是否使用 filled_qty 需驗證

---

## OPEN — TRADE-5：Hurst Exponent 不穩定導致策略權重頻繁切換

**來源**：改善報告 V3 Final（2026-04-03）
**嚴重性**：LOW
**問題**：Hurst 在 0.62→0.38→0.55 間跳動，Conductor 每次切換策略權重。每次切換有冷啟動期，期間表現最差。
**位置**：`app/hurst_exponent.py`、策略權重分配邏輯
**緩解**：可加 Hurst 平滑窗口或切換冷卻期

---

# ━━━ 安全 / 配置問題 ━━━

## RESOLVED — SEC-1：legacy_routes.py 殘留 detail=str(e) 信息洩露

**來源**：PA 技術審查（2026-04-01）
**嚴重性**：LOW
**問題**：`legacy_routes.py:680` 使用 `detail=str(exc)` 返回錯誤，可能洩露內部路徑
**位置**：`app/legacy_routes.py:680`
**修復**：替換為固定消息 + debug log（2026-04-03）

---

## RESOLVED — SEC-2：Reconciliation 虛假告警（13 條舊拒絕訂單）

**來源**：治理 / 授權修復日誌（2026-04-01）
**嚴重性**：LOW
**問題**：13 條舊的 REJECTED 狀態訂單持續觸發 FREEZE_TRADING 對賬建議
**位置**：`app/reconciliation_engine.py`
**修復**：`_reconcile_orders()` 過濾終態訂單（REJECTED/CANCELED/EXPIRED）（2026-04-03）

---

# ━━━ 代碼質量 / 技術債 ━━━

## OPEN — DEBT-1：legacy_routes.py 1276 行超出 1200 行硬上限

**來源**：重構日誌（2026-04-01）
**嚴重性**：LOW
**問題**：文件超出 CLAUDE.md §九 規定的 1200 行硬上限
**位置**：`app/legacy_routes.py`（1276 行）
**阻塞**：拆分需改變 `register_legacy_routes(app)` 模式，中等風險
**備註**：架構技術債，不影響功能

---

# ━━━ 已驗證為已修復的問題（歸檔參考）━━━
#
# 以下問題在審計報告中被標記為 OPEN，但經代碼驗證已修復：
#
# - E3-CRITICAL-2: _require_operator_role isinstance(dict) → 已改為 hasattr duck-typing（governance_routes.py:208）
# - P0-GAP-1: 學習反饋閉環 → 已在 0A-1 修復（phase2_strategy_routes.py:1056 注入 TruthSourceRegistry）
# - P0-GAP-2: 進化參數自動部署 → 已在 0A-2 修復
# - P1-GAP-3: H0 Gate shadow → 已在 0A-3 實現 shadow 觀察模式
# - P1-GAP-4: 交易所條件單 → 已在 0B-2 實現 SL/TP 雙重防線
# - P1-GAP-5: Scanner→Deployer → 已在 0A-4 確認接通
# - P1-GAP-6: Backtest 生產啟用 → 已在 0A-5 修復
# - P2-GAP-7: L2 門檻 50→20 → 已在 0A-6 修復
# - P0-FA-1: TruthSourceRegistry 注入 → 已在 phase2_strategy_routes.py:1056 注入 StrategistAgent
# - Grid theta=0 除零 → Python 和 Rust 均已有 max(0.001, -b) 守衛
# - 9 項 Bybit API 兼容性（qty_step/minOrderQty/positionIdx 等）→ 全部修復（commit 95b45f5）
# - 3 項 NaN/inf 安全漏洞 → 已修復（commit 9cc134a）
# - scout_routes.py async 阻塞 → 已修復（commit 87c2651）
# - Paper 授權重啟丟失 → 已修復（commit d065453）
# - Inverse PnL 公式 → 已修復（commit e9d0df8）
# - Paper→Demo 同步問題 → 已修復（commit ab31353）
