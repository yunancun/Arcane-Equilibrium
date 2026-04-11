# 已完成 TODO 歸檔 — W19 + W20 + Phase 6（截至 2026-04-11）

> 從 TODO.md 移出的已確認完成項。原文位於 `TODO.md` 各對應段落，本文件保留歷史原貌備查。
> 移出時間：2026-04-11（晚間 audit 後 housekeeping）

---

## 🔴 3E-E2 Fix Rounds — 多角色審計後修復計劃 ✅ 全部完成

**審計報告**：`docs/audits/2026-04-11--3e_arch_e2_multi_role_review.md`（633 行、9 角色平行審查）
**重審報告**：`docs/audits/2026-04-11--3e_arch_phase_g_reaudit.md`（9/9 PASS）
**核心結論**：3E-ARCH S0-S11 編譯/測試 pass（897 lib + 18 e2e + 2797 Python），但**實施不完整**：
1. **MEGA-BLOCKER-0**：當前 spawn 是「Primary + Paper alongside」，**非**用戶目標的「三者無條件並行」
2. **10 BLOCKER + 7 MAJOR + 6 MINOR** 覆蓋 D1-D26 架構缺口

**用戶 2026-04-11 架構澄清**：
- 唯一運行模式 = Paper/Demo/Live **三者同時並行**（各自依 API key 存在性獨立啟停）
- `trading_mode` / `TradingMode` enum / `primary_kind` **徹底刪除**，不留 deprecated 過渡
- 每個 Pipeline 啟動條件 = 自己的 API key + system_mode 允許

### Phase A — 快速修復（無架構依賴）✅
- [x] **BLOCKER-5** `settings_routes.py:391` `==` → `hmac.compare_digest(bytes, bytes)`（constant-time）
- [x] **BLOCKER-7** `settings_routes.py` 加 `_save_api_key_lock: asyncio.Lock`，衝突檢查→validate→write 串行
- [x] **BLOCKER-6** 遷移 5 處 `std::sync::RwLock` → `parking_lot::RwLock`
- [x] **MAJOR-1** `persistence.rs` StateWriter chmod 0600 + `#[cfg(unix)]` 回歸測試

### Phase B — 配置層補完 ✅
- [x] **BLOCKER-8** 創建 4 個 TOML 配置文件 + `StrategyFactory::create_for_engine(kind)` + 7 tests
- [x] **MAJOR-4** Paper balance 優先級解析統一（env > TOML > Demo API > 硬編碼 default）

### Phase C — 三引擎並行重構 · MEGA-BLOCKER-0 ✅
- [x] **3E-10.1** `main.rs` `determine_primary_kind()` 基於 API key 偵測取代 `config.trading_mode`
- [x] **3E-10.2** 刪除 `config.trading_mode` 字段 + `engine.toml` 清理
- [x] **3E-10.3** Python 側 serde rename `pipeline_kind` → `"trading_mode"` 兼容
- [x] **3E-10.4** Rust `TradingMode` enum 真正刪除
- [x] **3E-10.5** **BLOCKER-1 D19 DB 去重** — Demo/Live 管線 `market_data_tx`/`feature_tx`=`None`
- [x] **3E-10.6** **MINOR-2** `pipeline_cmd_tx_paper` 改名
- [x] **3E-10.7** reconciler_e2e 測試修復

### Phase D — 架構級補完 ✅
- [x] **BLOCKER-2** D6 三級遞減收縮（`EngineEvent::Crashed/CircuitBreakerTripped` + `PipelineHealth` atomic + `broadcast::channel`）
- [x] **BLOCKER-3** D15 `global_notional_cap_usdt`（`Arc<AtomicU64>` + Gate 2.7 後檢查）
- [x] **BLOCKER-4** D17 Live 獨立 tokio Runtime（`std::thread` + `worker_threads(2)`）
- [x] **MAJOR-2** 啟動競態（`oneshot::channel` per-pipeline ready + 60s 超時）
- [x] **MAJOR-3** shutdown 分級（WS+IPC → Primary → Paper, 10s + Live thread join）
- [x] **MAJOR-5** IPC per-engine audit log
- [x] **MAJOR-7** snapshot `schema_version: "2.0.0"` + `written_at_ms`

### Phase E — 測試補完 ✅
- [x] **BLOCKER-10** 補 25 blocker tests（D2/D6/D15/D23 全覆蓋）
- [x] 全測試套件跑通 1313 passed / 0 failed

### Phase F — 文件拆分 ✅
- [x] **BLOCKER-9** 5 個超 1200 硬上限文件全部拆分為目錄模組

### Phase G — 重跑驗收 ✅
- [x] 9 角色並行 3E-E2 重審 — **9/9 PASS**
- [x] 殘留修復：M-3 GovernanceProfile / M-4 catch_unwind / 8 MINOR 修復
- **殘留 2 MAJOR**（M-1/M-2 文件大小監控，非阻塞，下次加 handler 前處理）

---

## 🛡️ W19 — 安全 + 告警 ✅ 全部完成

### W19-P0：IPC 認證 + Rate Limiting

- [x] **SEC-05** GUI `innerHTML` XSS — ocEsc() 全量包裹
- [x] **SEC-17** `OPENCLAW_ALLOW_MAINNET` 移除 — API key 填入 = 唯一上線條件
- [x] **G-3 / SEC-08** IPC socket HMAC-SHA256 認證
  - `verify_ipc_token()` 常數時間 + `handle_connection` auth + Python `_authenticate()` + fail-closed + 向後兼容
- [x] **G-5** API Rate Limiting — `main_legacy.py:304-307` `default_limits=[120/min]` 全 214 路由覆蓋

### W19-P0：告警通道（阻塞 6-RC-6）

- [x] **OC-3** 多通道分級告警 — `reconciler_alert_monitor()` 30s 輪詢 + tier 映射
- [x] **6-RC-6** 多通道告警 + governor tier 升降 — OC-3 覆蓋

---

## 🛡️ W20 — 深度安全審查 ✅

- [x] **SEC-04 / 06 / 13** 深度 E3 審查 — 04 safe (parameterized) / 06 fixed (HttpOnly) / 13 fixed (saturating cast)
- [x] **G-9** HMAC dead import 確認 — NOT dead，L171 auth token 驗證
- [x] **WP-CC/FS-1 / BI-1 / P9 / SM-1**
  - FS-1 tests 提取（1083→742 行）
  - BI-1 MODULE_NOTE 12 files
  - P9 雙軌止損 StopRequest→PositionManager 接線
  - SM-1 Singleton 合規

---

## 📈 Phase 6 — Reconciler 自動 governor 動作層 ✅

### 6-RC（W20-W21 完成）

- [x] **6-RC-1** ReconcilerEscalate/DeEscalate 動作通道隔離
- [x] **6-RC-2** V014 event_type 隔離
- [x] **6-RC-3** 動作策略（MajorDrift→Cautious / burst→CB+CloseAll）
- [x] **6-RC-4** 自身冷卻（per-symbol 30min + 全局 5min + hybrid 恢復）
- [x] **6-RC-5** Per-symbol minQty dust floor
- [x] **6-RC-6** 多通道告警 + governor tier 升降告警（W19 OC-3 覆蓋）
- [x] **6-RC-7** 整合測試（7 場景 reconciler_e2e.rs）
- [x] **6-RC-8** Live blocker 解除
- [x] **6-RC-9** Baseline staleness 政策
- [x] **6-RC-10** REST 失敗升級（≥10 次→Cautious）

### 6-Phase 漸進放權（W20-W21）

- [x] **6-01~03** 漸進放權管線 — `promotion_pipeline.py` (PromotionGate + 5 stages + graduation gates + operator approval) + 3 API endpoints + 27 tests
- [x] **6-04** 集成測試（reconciler_e2e.rs 7 新場景）
- [x] **6-05** 壓測（Rust 4 場景 + Python 5 場景）
- [x] **6-06** sync_commit Live 驗證 PASS — global `synchronous_commit=on`（V006:90）
- [x] **6-07~08** EvolutionEngine 保留（DL/AI agent 學習）+ PromotionPipeline 分工文檔化

---

## ✅ WP-F GUI（小修）

- [x] **WP-F/AH-06** Risk-tab dirty-tracking

---

---

## 🔴 2026-04-11 晚間 Audit BLOCKERs ✅ 全部已修（2026-04-12 歸檔）

**起源**：用戶要求「仔細檢查現在的持倉和今天的交易，看看是否風控全都在有效接入」→ 9 角色 audit 發現 4 MAJOR + 2 BLOCKER。M-1~M-4 + B-1 + B-2 全部修復完畢。

- [x] **B-1 Demo/Live 快照 positions 空（startup 不導入既存倉 + WS PositionUpdate 未寫回）** ✅ FIXED 2026-04-12（commit f6e7afc, Phase 2）
  - 根因：startup seeding 缺失 + WS PositionUpdate 不寫回。修復：`paper_state.import_positions()` + `upsert_position_from_exchange()` + `ExchangeEvent::PositionUpdate` 新增變體。驗證：demo positions=12 + live positions=9 與 Bybit 一致。+2 tests。935 lib pass。

- [x] **B-2 total_fills 不遞增（exchange 模式）** ✅ FIXED 2026-04-11（commits 8e08c34 / b5e45f7 / 152d1f6）
  - 根因：Bybit demo 不支援 `execution.fast` topic + typo `fast-execution`。修復：環境感知 topic 選擇 + parser 日誌改善 + Live worker_threads 2→4。驗證：demo 6min 收到 18 筆真實 WS fills。

- [x] **M-1** `order_manager.validate_and_round` fail-closed 缺 spec + `dispatch.rs` Market 訂單 pre-flight 名義值檢查
- [x] **M-2** `grid_trading.on_rejection` per-symbol 30s 拒絕冷卻 + `on_tick.rs` post-Guardian capped qty 顯示
- [x] **M-3** cost_gate 跨引擎驗證 — 日誌證據確認設計正確運作（無代碼變更）
- [x] **M-4** `risk_config_live.toml` 限額驗證 — 全部正確收緊

---

## 📈 Phase 6 — 6-09~13 PM 驗收 ✅（2026-04-12 歸檔）

- [x] **6-09~13** E2 + E4 + QA 端到端 + E5 + PM 驗收（2026-04-12 PM sign-off PASS）
  - E4: 935 engine lib + 366 core + 18 e2e + 32 promotion = 1351 passed / 0 failed / 0 warnings
  - E2: Reconciler 0 BLOCKER 0 MAJOR · Promotion 0 BLOCKER 0 MAJOR（governance_routes 超限 pre-existing）
  - QA: 三引擎存活 + 雙 Reconciler 運行 + baseline seeded + API auth enforced
  - E5: stress test PASS（1000 calls <100ms）· 32 promotion tests 0.06s

---

**歸檔依據**：2026-04-11 晚間 audit 後 TODO 整理 + 2026-04-12 Phase 6 PM 驗收完成後追加歸檔。全部標記 `[x]` 的 W19/W20/Phase 6 / 3E-E2 Fix Rounds / 晚間 Audit 子項移入此檔，TODO.md 僅保留 `[ ]` 工作項與精簡摘要。
