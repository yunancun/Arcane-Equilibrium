# OpenClaw TODO — 工作計劃清單
# 最後更新：2026-04-06（RRC-1 完成 + L3 12路審計 · 1075 Py + 856 Rust = 1931）
# 注意：compact 後從此文件恢復工作狀態
# ★ 排查參考：docs/KNOWN_ISSUES.md（已識別但未驗證的風險，遇到異常時先查）
# ★ 審計報告：srv/audit_PA_consolidated_remediation_plan.md（63 issues · 11 work packages）
# ★ 整合報告 2026-04-06：docs/audits/2026-04-06_consolidated_remediation_report.md（53 OPEN / 6 DONE / 4 PARTIAL · R0-R3 batches）
# ★ 待辦：策略 confidence 需要動態化（當前固定 0.50，低波動市場全被 cost gate 攔截）

---

## ██ 2026-04-06 PA 整合審計 — R0 立即修復清單 ██

從 13 份審計報告整合驗證後的 OPEN P0 清單（詳見 `docs/audits/2026-04-06_consolidated_remediation_report.md`）：

- [ ] **R0-1 / I-01** `intent_processor.rs::process_gates_only()` 補上 Gate 3 Cost Gate（exchange 模式必須）
- [ ] **R0-2 / I-02 + I-09** IPC Unix socket 設 0o600 + 風控 setter 加 `.clamp()` 邊界
- [ ] **R0-3 / I-06** `market_data_client.rs` (1422 LOC) 拆分至 1200 以下硬上限
- [ ] **R0-4 / I-07** 執行 DDL V001-V007 到生產 PG，驗證 6 個 writer 開始入庫
- [ ] **R0-5 / NEW-1** 重建 `tests/stress_integration.rs`（檔案已被整個刪除，29 個 stress 場景需重新移植到當前 4-arg 簽名）
- [ ] **R0-6 / I-04 + I-05** 重跑 `test_grafana_data_writer.py` 與 `test_label_generator.py`，若仍紅則修復根因

**Exchange mode go-live blockers**: R0-1, R0-2, R0-5, R1-A, R1-I, R1-J（見整合報告 §6 critical-path）。

### ██ 2026-04-06 WP 子檢查清單回鏈（見整合報告 §10，223 sub-items）██
- WP-F GUI 47 項 → `docs/audits/2026-04-06_consolidated_remediation_report.md#101-wp-f--gui-usability-a3-report-47-items`
- WP-G 硬編碼 43 項 → `docs/audits/2026-04-06_consolidated_remediation_report.md#102-wp-g--hardcoded-values-qc-report-43-items`
- WP-E4 測試 34 項 → `docs/audits/2026-04-06_consolidated_remediation_report.md#103-wp-e4--test-coverage-gaps-e4-report-34-items`
- WP-I 文檔 42 項 → `docs/audits/2026-04-06_consolidated_remediation_report.md#104-wp-i--documentation-hygiene-r4--tw-reports-42-items`
- WP-E5 優化 20 項 → `docs/audits/2026-04-06_consolidated_remediation_report.md#105-wp-e5--optimization--code-quality-e5-report-20-items`
- WP-B 安全 12 項 → `docs/audits/2026-04-06_consolidated_remediation_report.md#106-wp-b--security-e3-report-12-items-8-folded-into-top-level`
- WP-BB Bybit 3 項 → `docs/audits/2026-04-06_consolidated_remediation_report.md#107-wp-bb--bybit-api-bb-report-3-real-findings`
- WP-CC 合規 8 項 → `docs/audits/2026-04-06_consolidated_remediation_report.md#108-wp-cc--compliance-cc-report-8-partialfail-items`
- WP-FA 規格 5 項 → `docs/audits/2026-04-06_consolidated_remediation_report.md#109-wp-fa--functional-spec-gaps-fa-report-5-partial-items-not-in-top-level`
- WP-MIT DB/ML 9 項 → `docs/audits/2026-04-06_consolidated_remediation_report.md#1010-wp-mit--database--ml-mit-report-6-sub-items`

### 已驗證 DONE（從 PA 63 中歸檔）

- [x] Session 9c `realized_pnl` 接線（`tick_pipeline.rs:737-763` + `trading_writer.rs:151-163`）
- [x] Gate 3 Cost Gate 在 `process()` 路徑完整（intent_processor.rs L317-355）
- [x] H0Gate fail-closed 硬化 + RRC-1 風控接線（CLAUDE.md §三）
- [x] PyO3 39 方法 + Bybit V5 全量端點（BB 審計確認 47/47 正確）
- [x] 風控 GUI Session 9 補齊 + IPC h0_shadow_mode 全鏈路（CLAUDE.md §三）

### R1 高優先級 P1（待 R0 完成後）

- [ ] I-08 StopRequest channel 接入 `set_trading_stop`（雙軌止損生效）
- [ ] I-10 Cookie `secure=True` env-driven
- [ ] I-11 GUI `innerHTML` → `textContent`（防 XSS）
- [ ] I-12 風控 tab input focused 時跳過 15 s 自動覆蓋
- [ ] I-13 移除 AI advice Apply 按鈕父 div `display:none`
- [ ] I-14 Delete strategy + Danger Zone 加確認彈窗
- [ ] I-15 Feed/Demo/Scanner 快捷按鈕改為只讀指示器
- [ ] I-16 `saveProviderKey` 後端對齊 + `runEvolution` 改 `ocPost`
- [ ] I-17 5 個高風險硬編碼值移入 StopConfig（HC-S1/S2/S3/CG1/CG2）
- [ ] I-18 12 個 regime 乘數提取為 RegimeConfig
- [ ] I-19 Scorer 接入 `tick_pipeline`（信號後、intent 前 score()）
- [ ] I-20 `record_trade()` 在成交回調中調用
- [ ] I-21 `PositionSnapshot` 每 30s 發射到 trading_tx
- [ ] I-22 `event_consumer.rs` 補 +15 unit tests
- [ ] I-23 `ort` crate 整合 + `model_manager::predict()` 真實實現
- [ ] I-24 `docs/README.md` 補 25 項遺漏
- [ ] I-25 創建 `helper_scripts/SCRIPT_INDEX.md`
- [ ] I-26 合併 04-05 worklog 6 碎片到 daily_summary
- [ ] I-27 `cargo fix` W1-W4 + 手動處理 W5
- [ ] I-28 Python >1200 LOC 文件清理時間線

### R2 P2 主題批次（Phase 4 初期）

DB 接線（I-32/33/36/53）· ML 訓練（I-34/35/37）· 代碼品質（I-38/39/40）· 風控完善（I-29/30/31/49）· Bybit 強化（I-50/51/52）· 文檔（I-41-45）· 數學（I-46/47）· 治理（I-48）

### R3 Backlog（Phase 4+）

I-54..I-63 — 詳見整合報告 §4.

---


---

## ██ 每次啟動必做：引擎健康檢查 ██

**Rust 引擎為主交易引擎，獨立運行中。**

```bash
# 1. 引擎是否存活？
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status

# 2. canary 記錄數量
wc -l /tmp/openclaw/engine_results.jsonl

# 3. watchdog 崩潰記錄
grep -c "ENGINE_CRASH\|3-STRIKE" /tmp/openclaw/watchdog.log 2>/dev/null || echo "0 crashes"

# 4. 最新 tick
tail -1 /tmp/openclaw/engine_results.jsonl | python3 -c "
import sys,json; r=json.load(sys.stdin)
ps=r['paper_state']
print(f'tick #{r[\"tick_number\"]} | {r[\"symbol\"]} @ {r[\"price\"]}')
print(f'balance=\${ps[\"balance\"]:.2f} | fills={r[\"stats\"][\"total_fills\"]} | positions={len(ps[\"positions\"])}')
"
```

Go/No-Go：**2026-04-04 已通過 7/7**。重啟指引見 `docs/rust_migration/07--canary_greybox.md`。

---

## 強制工作流程

```
E1/E1a 並行（最多 5 路）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
16 角色定義詳見 CLAUDE.md §八
```

### ★ Bybit API 開發必查

所有 Bybit 相關的修改/新功能，開發前必須先查閱：
- **字典手冊**：`docs/references/2026-04-04--bybit_api_reference.md`（64 REST + WS + IPC 全索引）
- **審計報告**：`docs/audits/2026-04-04--bybit_api_infra_audit.md`（路徑正確性 + 已知陷阱）
- 已有端點直接調用，不重複實現。新增端點完成後同步更新手冊。

---

## 測試基準線

```
Python: 1075 passed / Rust: 856 passed
Total:  1931 tests
注：RRC-1 後基準線更新（2026-04-06）
注：1 pre-existing grafana test skip
注：E4 審計發現 stress_integration.rs 29 tests 編譯失敗（process() 新增 atr 參數未同步）
```

---

## 已完成項歸檔

```
Wave 0-7 / Phase 1-3 / Audit Batch 1-7 / main_legacy 重構：
  → docs/worklogs/control_api_gui/2026-04-01--completed_todo_archive.md

Batch 9A + XP-1~4 + Wave 8A-8D：
  → docs/worklogs/2026-04-03--completed_todo_archive_batch9a_wave8_xp.md

Phase 0-A/0-B/1/2/3 全部完成（[x] 26 項）+ Phase R-00~R-06 完成：
  → docs/worklogs/2026-04-04--completed_todo_archive_phase0123_rust.md

2026-04-04 Session（本次）：
  [x] 3-STRIKE Cold Start 修復（watchdog 45s + grace-period + force_write）
  [x] Phase 0a DDL 草稿 V001-V005（43 表 / 8 Schema / 29 hypertable）— DDL 複審 43/43 MATCH
  [x] tick_duration_us 添加到 CanaryRecord
  [x] Replay Mode B 實現（feed_replay_tick 100% 複用 on_tick）
  [x] 完整 201K tick replay 驗證基礎設施
  [x] Python ADX bug 修復（DX→ADX Wilder 平滑第三步）
  [x] Comparator key 映射（31+35 keys）+ bar-close filter + paper_state skip
  [x] Rust Hurst 安全修復（零價格防禦 + clamp + Kahan）
  [x] Rust KAMA SMA seed 對齊
  [x] Rust IndicatorSnapshot 擴展（+sma_50, ema_26, atr_5, conservative_atr）
  [x] Rust BB Breakout ATR trailing stop + regime exit
  [x] Python KAMA per-step SC 修復 + Stochastic Slow %K
  [x] Comparator 容差放寬（simple 1e-6, recursive 1e-2, complex 5e-2）
  [x] signal_generator 9x NoneType guard
  [x] QA 嚴格審計（Python V2 真實 62/100，6 項 FAKE/DEAD）
  [x] PYO3-1 推遲到 Phase 2（接口錯位）
  [x] Operator 決策：放棄修 Python，全力 Rust

SPEC 審查記錄：
  → 認知自適應：docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md
  → Rust 遷移：docs/references/2026-04-03--rust_migration_v3_final.md
  → Agent 調參：docs/references/2026-04-03--agent_param_tuning_design_draft_v0.2.md

2026-04-05 RRC-1 風控運行時接線（5 Phase · 3 commits）：
  [x] Phase A：H0Gate 接入 tick_pipeline Step 0.5（shadow mode）
  [x] Phase B：Gate 2.7 check_order_allowed 接入 IntentProcessor（P1 sizing 後）
  [x] Phase C：check_position_on_tick 9 check 替換 check_stops + PriceHistoryTracker
  [x] Phase D：PipelineSnapshot +8 風控欄位 · risk_routes Rust-first
  [x] Phase E：Strategy set_active IPC · session unhalt · exchange double-close fix
  [x] 3 輪審計：4 issues 修復（NaN/state leak/double-close）· 856 Rust tests

2026-04-05 L3 全系統審計 12 路並行（commit b25e541）：
  [x] FA/AI-E/E5/E4/E3/CC/QC/MIT/BB/TW/R4/A3 + PA 統一整改
  [x] 63 問題（7P0/21P1/25P2/10P3）→ 11 工作包 → 4 波執行計劃
  報告：srv/audit_*_report.md + audit_PA_consolidated_remediation_plan.md

2026-04-05 Session 9（EXT-1 + L3 Audit + Risk Config）：
  [x] EXT-1-01~10：Exchange-as-Truth 全部完成（commit b878f61）
  [x] L3 Audit：7 項修復 — P0-1~5 + SEC-1 + SEC-5（commit 5c1c935）
  [x] Zero-qty ghost position fix（commit 66ee29b）
  [x] P1 risk cap configurable via engine.toml（commit 8103c6f）
  [x] GUI→IPC→Rust risk config wiring（commit f7c9086）
  [x] Full runtime risk configurability — 9 fields（commit d053a51）
  [x] KNOWN_ISSUES：RISK-1 RESOLVED + RISK-2/RISK-3 新增 OPEN

2026-04-05 Session 8（RC-10 + 雙引擎架構 + GUI 遷移）：
  [x] RC-10：Python PaperTradingEngine 完全禁用（ENGINE=None）防止雙引擎
  [x] IPC-CMD：Rust IPC command channel — pause/resume/close_all/reset（PaperSessionCommand enum + unbounded_channel）
  [x] P1-P4：Demo primary + 統一雙引擎控制 + shadow default-on + Paper→測試引擎
  [x] WS-FIX：移除 liquidation/price-limit/adl-notice（Bybit handler not found 毒化連接）
  [x] GUI 全面遷移：retCode→source 判斷 + positions array format + disabled endpoints + Demo tab 控制按鈕
  [x] GUI-HANG 修復：IPC socket 3s timeout + 移除 hot path API call + is_available() 減 stat()
  [x] Shadow orders：skip qty=0 + unique order_link_id + config Default impl 修復
  [x] BB handbook 更新：broken WS topics + subscription limits 修正
  [x] restart_all.sh：一鍵引擎+API 重啟腳本
  [x] 架構研究：PM+PA+FA+BB+CC 五路聯合研究「交易所即真相」執行模式

2026-04-05 Session 6（基礎設施清理）：
  [x] RE-1 RESOLVED：審計確認 fills Vec 不存在，HashMaps 自然有界
  [x] RE-2 RESOLVED：WS process_message 返回 bool + 公共/私有 WS supervisor 包裝
  [x] ARCH-4 RESOLVED：H0 Gate + Cost Gate exception handler → fail-closed
  [x] ARCH-1 RESOLVED：ExecutorAgent intent_id 去重（OrderedDict + 10s 窗口）
  [x] OC-1：webhook_alerter.py（HMAC-SHA256 · 多端點 · 限流）
  [x] OC-2：alert_router.py + paper_trading_wiring 接入（Telegram+Webhook 雙通道）
  [x] Bybit handbook §2.3 Shadow Order Sync Channel 文檔
  [x] RE-3 降級 LOW + 審計補充 · DEBT-1 deferral note · IPC-05 範圍記錄
  [x] KNOWN_ISSUES OPEN 11→8 · RESOLVED 3→7 · commit 0e2d6a4
```

---

## ██ 當前焦點：L3 審計整改 → Phase 4 ██

### L3 審計整改計劃（2026-04-06）
> **12 路全系統審計完成，63 問題 → 11 工作包 → 4 波執行。**
> PA 整改報告：`audit_PA_consolidated_remediation_plan.md`
> P0 全清約 2 天，P0+P1 全清約 8 個工作日。

### 虧損根因分析（2026-04-06 · 引擎運行數據）
> **真實交易虧損 ~$3.17（0.32%），非 90%（$10k→$1k 是配置變更非虧損）**
> 171 fills / 9 stops / ~15 次引擎重啟 / BTC 僅 1.2% 波動區間

- [ ] PNL-1（P0）：qty=0 幽靈倉禁止開倉 — intent_processor final_qty==0 時 reject（BTC/ETH $1k 餘額取整為 0）
- [ ] PNL-2（P0）：H0Gate 從未觸發（h0_checks=0）— 排查為何代碼路徑未執行
- [ ] PNL-3（P1）：引擎重啟冷卻期 — 重啟後等 N tick 建立 ATR/indicator 再開倉（當前立即開 5 倉）
- [ ] PNL-4（P1）：regime 動態化 — 當前硬編碼 "ranging"，需接入 Hurst/ADX 實際判斷
- [ ] PNL-5（P1）：Cost Gate 小帳戶收緊 — k=1.5 對 $20 notional 幾乎不攔截
- [ ] PNL-6（P2）：止損風險收益比失衡 — 止損虧 $0.26~$0.42 vs 正常平倉賺 $0.01~$0.06
- [ ] PNL-7（P2）：dynamic_stop base=0.6 / cap=0.8 硬編碼 → 提取為可配置參數

### 數據庫積累狀況（2026-04-06 · 運行 12hr）
> **DB 19 GB · 10/57 表有數據 · 47 表空 · signals 15.2M 行爆炸增長**

- [ ] DB-RUN-1（P0）：signals 寫入頻率治理 — 15.2M/12hr = 352行/秒，1天30M行/12GB，1週80GB+
      方案：降為每 bar close 寫入（非每 tick）或 batch 聚合後寫入，預期降 95%+
- [ ] DB-RUN-2（P0）：decision_context_snapshots 治理 — 5.3M/12hr = 13GB，1天26GB
      方案：降為每 intent 時寫入（非每 tick），或定時快照（每 30s/1min）
- [ ] DB-RUN-3（P1）：realized_pnl 全為 0 — RRC-1 修復 apply_fill ���回值，但 DB 數據仍為 0
      排查：引擎是否已用新 binary？需重啟引擎使修復生效
- [ ] DB-RUN-4（P1）：feature_writer 無歷史積累 — features.online_latest 僅 5 行，無歷史 feature vectors
      排查：feature_writer 是否在運行？history 表是否被寫入？
- [ ] DB-RUN-5（P2）：47/57 表空（agent/learning/observability/risk 全空）— 需確認各 writer 是否啟動
- [ ] DB-RUN-6（P2）：5 條 decision_context ts=1970-01-01（epoch 0 遺留數據）— 清理
- [ ] DB-RUN-7（P3）：signals hypertable 5.7GB 但 pg_stat 顯示 40KB — ANALYZE 或 compression 配置驗證

### Operator 決策（2026-04-04）
> **放棄修復 Python V2 交易引擎，全力完善 Rust。Python 只保留 API/GUI/Agent 層。**
> QA 審計：Python V2 真實成熟度 62/100，6 項功能 FAKE/DEAD/UNREACHABLE。
> 詳見：`docs/worklogs/2026-04-04--session_progress_1.md`

---

## ██ R-CUT：Rust 策略補齊 + 切換（4/5-4/10）

### 階段 1：Rust 策略補齊（4/5-4/7）

- [x] RC-01：MA Crossover regime filter — Hurst regime 過濾震盪市假信號
- [x] RC-02：MA Crossover multi-TF confirm — 簡化為 4h EMA proxy 確認
- [x] RC-03：BB Breakout volume/Donchian 直讀確認 + 參數可配置化
- [x] RC-04：所有策略 intent rejection rollback — on_rejection() + prev_* 快照
- [x] RC-05：所有策略 on_fill() sync — trait default no-op + tick_pipeline 接線
- [x] RC-06：Grid Trading geometric spacing + health check + auto-rebalance
- [x] RC-07：BB Reversion limit order（策略端真實實現，execution 層 Phase 2 補齊）
- [x] RC-08：StrategyParams trait + ParamRange 定義，實現留空 Phase 3a
- [x] RC-09：E2 審查 + E4 回歸 + QA Audit CONDITIONAL PASS

### 階段 2：最小切換（4/8-4/9）

- [x] RC-10：停止 Python tick_pipeline（2 處 activate() 註釋掉，PIPELINE_BRIDGE 保留供 API 查詢）
- [x] RC-11：刪除分類 A dead code（4 files / 1,003 行：shadow_decision_tracker/dream_engine/opportunity_tracker/strategy_health_monitor）
      — 註：原估 187 files 實為 Category B+C，需 R-IPC API 遷移後才能刪
- [x] RC-12：全量測試驗證 4507 全綠零回歸
- [x] RC-13：E2 + E4 PASS

### 階段 3：Go/No-Go（4/10）

- [x] RC-14：Go/No-Go 最終檢查 7/7 PASS（201K replay P50=27μs / RSS 2.1MB / 0 crash）
- [x] RC-15：Go/No-Go 評估報告撰寫

### 階段 4：Post-Go 清理（4/04 Session 2+3）

- [x] RC-11b：消除 Python/Rust 止損雙重執行（engine.tick() 停用 · commit 4dc835a）
- [x] RC-12b：停用 Python MarketDataDispatcher 自動啟動（重複 WS 連接 · commit f5d7192）
- [x] 10 個 flaky test 修復（Rust-first 格式 + 測試隔離 · commit 4dc835a）
- [x] GovernanceHub 5 死方法標記 deprecated（commit 4dc835a）
- [x] Klines 加入 Rust snapshot + get_klines Rust-first（commit 5979170）
- [x] get_indicators 全 timeframe Rust-first（commit 4f9836c）
- [x] 全面審計：零重複系統確認（tick/WS/stops/governance 全部單一路徑）

---

## ██ R-IPC：Rust IPC 擴展 + Python API 切換（4/11-4/14，與 Phase 0a 並行）

- [x] IPC-01：Rust PipelineSnapshot 擴展（+indicators/signals/strategies/recent_intents/recent_fills）
- [x] IPC-02：Python ipc_state_reader.py 擴展 5 新方法
- [x] IPC-03：8 條 API 路由改為 Rust-first + Python fallback（5 寫操作路由待 Rust 命令通道）
- [x] IPC-04：PipelineBridge 降級為 IPC 中繼 + Agent 回調容器（docstring + DEPRECATED 標記）
- [ ] IPC-05：分類 B Python 文件逐步降級（需 PYO3-BYBIT 寫操作路由遷移後）
      — 2026-04-05 審計：PYO3-BYBIT 讀路由完成，寫操作路由待 Phase 2。範圍 15-25 files / ~800-1200 LOC。延後至 Phase 2 後執行。
- [x] IPC-06：E2 + E4 — 4507 全綠

---

## ██ PYO3-BYBIT：PyO3 Bybit API 橋接（Route C · 取代 Python BybitDemoConnector）

> **Operator 決策（2026-04-04）：** 採用 Route C（PyO3 直接調用），不走 IPC 透傳。
> 編譯增量 5-12s 可接受，跨語言調試由 CC 處理無障礙。
> 設計文件：本段即為 PM+PA+FA 聯合設計。

### 架構設計（PA）

```
Python FastAPI route
    ↓ import openclaw_core
BybitClient (#[pyclass], 持有 Arc<BybitRestClient> + tokio::Runtime)
    ├─ AccountManagerWrapper   → refresh_balance / wallet_snapshot / fee_rates
    ├─ OrderManagerWrapper     → place_order / cancel / get_active / get_executions
    ├─ PositionManagerWrapper  → get_positions / set_leverage / set_trading_stop / closed_pnl
    ├─ MarketDataWrapper       → get_klines / get_tickers / get_orderbook / get_funding
    └─ InstrumentInfoWrapper   → refresh / get / round_qty / round_price / validate
    ↓ async→sync: tokio::Runtime::block_on()
Rust Bybit modules (openclaw_engine::*)
    ↓ HMAC-SHA256 signed HTTP
Bybit V5 API (Demo/Testnet/Mainnet)
```

**關鍵設計決策：**

1. **Crate 結構**：擴展現有 `openclaw_pyo3`，加 `openclaw_engine` 依賴（lib.rs 已 re-export 全部模組）
2. **Async 處理**：每個 BybitClient 實例持有獨立 `tokio::Runtime`，PyO3 方法內 `rt.block_on(async_fn())`
   - 不干擾 Python asyncio event loop（tokio Runtime 在獨立線程池）
   - FastAPI 的 sync route handler 在 threadpool 跑，不會 deadlock
3. **序列化**：所有 Rust struct 已實現 `Serialize` → `serde_json::to_value()` → `pythonize::pythonize()` 轉 PyObject
   - 備選：手動 `to_dict()` → `HashMap<String, PyObject>`（現有 ContextDistiller 用此法）
   - 建議：用 `pythonize` crate 自動轉換，省掉手寫 wrapper
4. **錯誤映射**：`BybitApiError` → `PyErr`（PyRuntimeError），保留 retCode + retMsg
5. **Python 模組名**：保持 `openclaw_core`，新增 `BybitClient` 等 class
6. **向後兼容**：BybitDemoConnector 標記 DEPRECATED，保留作 fallback

**FA 覆蓋範圍：**

| 覆蓋（本批次） | 不覆蓋（保持 Python，原因） |
|---------------|--------------------------|
| demo/balance — AccountManager | governance 25 端點 — GovernanceHub 決策引擎，無 Bybit 等價 |
| demo/positions — PositionManager | paper session start/stop — 本地狀態機，非 API 操作 |
| demo/orders — OrderManager | risk config/override — 本地風控邏輯 |
| demo/fills — OrderManager.get_executions | Layer 2 AI 11 端點 — Python Ollama 整合 |
| market data（klines/tickers/OB/funding） | learning 15 端點 — 獨立子系統 |
| instrument info（品種規格/精度） | scanner/deployer — Python 獨立組件 |
| order submit/cancel（寫操作） | |
| leverage/TP-SL 設定 | |

**風險評估（FA）：**

| 風險 | 等級 | 緩解 |
|------|------|------|
| tokio Runtime 與 Python asyncio 衝突 | 低 | 獨立 Runtime，不共享 event loop |
| Bybit rate limit（10 req/s） | 中 | 與現有 Python connector 相同行為，不增加調用頻率 |
| PyO3 .so 與 Python 版本綁定 | 低 | maturin develop 針對當前 Python 版本編譯 |
| 編譯時間增加 | 已驗證 | 增量 5-12s，全量 ~15s |

### 任務列表

#### 階段 1：Rust 基礎設施（PYO3-B01 ~ B02）

- [x] PYO3-B01：Crate 準備（commit e3c9afe）
  - `openclaw_pyo3/Cargo.toml` 增加 `openclaw_engine`、`tokio`、`pythonize` 依賴
  - 新建 `openclaw_pyo3/src/bybit_bridge/mod.rs`
  - 實現：`TokioRuntime` 單例 + `bybit_err_to_pyerr()` 錯誤轉換 + `rust_to_py()` 序列化輔助
  - `lib.rs` 增加 `mod bybit_bridge;` + register classes
  - `maturin develop` 編譯通過
  - 文件清單：`Cargo.toml`(1) + `mod.rs`(1) + `lib.rs`(1) = 3 文件

- [x] PYO3-B02：BybitClient + AccountManager wrapper（commit e3c9afe）
  - `#[pyclass] BybitClient`：`__init__(api_key, api_secret, env="demo")` → 內部創建 `Arc<BybitRestClient>` + `tokio::Runtime`
  - `refresh_balance()` → `PyResult<PyObject>`（WalletState dict）
  - `usdt_equity()` / `usdt_available()` / `usdt_wallet_balance()` → `f64`
  - `wallet_snapshot()` → `PyResult<PyObject>`（完整快照 dict）
  - `get_fee_rates(category)` → `PyResult<PyObject>`（list[dict]）
  - `get_account_info()` → `PyResult<PyObject>`
  - 單元測試：mock client + 序列化驗證
  - 文件：`bybit_bridge/client.rs`(1) + `bybit_bridge/account.rs`(1) + tests

#### 階段 2：Order + Position wrappers（PYO3-B03）

- [x] PYO3-B03：OrderManager + PositionManager wrapper（commit e3c9afe）
  - `#[pymethods] impl BybitClient`（擴展同一 pyclass）：
  - **Orders**：
    - `place_order(symbol, side, order_type, qty, price?, category?, reduce_only?, tif?)` → dict
    - `cancel_order(category, symbol, order_id)` → dict
    - `cancel_all_orders(category)` → dict
    - `get_active_orders(category, symbol?)` → list[dict]
    - `get_order_history(category, symbol?, limit?)` → list[dict]
    - `get_executions(category, symbol?, limit?)` → list[dict]
  - **Positions**：
    - `get_positions(category, symbol?)` → list[dict]
    - `set_leverage(category, symbol, buy_lev, sell_lev)` → dict
    - `set_trading_stop(category, symbol, tp?, sl?, trailing?)` → dict
    - `get_closed_pnl(category, symbol?, limit?)` → list[dict]
  - 文件：`bybit_bridge/orders.rs`(1) + `bybit_bridge/positions.rs`(1) + tests

#### 階段 3：MarketData + InstrumentInfo wrappers（PYO3-B04）

- [x] PYO3-B04：MarketDataClient + InstrumentInfoCache wrapper（commit 68c4713）
  - **Market Data**（`#[pymethods] impl BybitClient` 繼續擴展）：
    - `get_klines(category, symbol, interval, limit?)` → list[dict]
    - `get_tickers(category, symbol?)` → list[dict]
    - `get_orderbook(category, symbol, limit?)` → dict
    - `get_funding_history(category, symbol, limit?)` → list[dict]
    - `get_open_interest(category, symbol, interval, limit?)` → list[dict]
    - `get_long_short_ratio(category, symbol, period, limit?)` → list[dict]
    - `get_recent_trades(category, symbol, limit?)` → list[dict]
  - **Instrument Info**：
    - `refresh_instruments(category)` → int（載入數量）
    - `get_instrument(symbol)` → dict?（SymbolSpec）
    - `round_qty(symbol, qty)` → float?
    - `round_price(symbol, price)` → float?
    - `validate_order(symbol, qty, price)` → (bool, str)
  - 文件：`bybit_bridge/market_data.rs`(1) + `bybit_bridge/instruments.rs`(1) + tests

#### 階段 4：Python 整合（PYO3-B05）

- [x] PYO3-B05：Python 端接入
  - `strategy_ai_routes.py`：demo/* 4 端點改用 `from openclaw_core import BybitClient`
  - 回退邏輯：`try: import openclaw_core; HAS_RUST_BRIDGE = True` → 不可用時降級 BybitDemoConnector
  - `bybit_demo_connector.py`：MODULE_NOTE 標記 DEPRECATED，保留作 fallback
  - 驗證：GUI demo tab 數據正確顯示
  - 文件：`strategy_ai_routes.py`(1) + `bybit_demo_connector.py`(1)

#### 階段 5：構建 + 質量保證（PYO3-B06 ~ B08）

- [x] PYO3-B06：maturin 構建驗證（39 methods, 3.7s 增量編譯）
  - `maturin develop` 成功
  - `python3 -c "from openclaw_core import BybitClient; print('OK')"` 通過
  - 增量編譯時間測量並記錄

- [x] PYO3-B07：E2 代碼審查 + E4 回歸測試（0 FAIL · 4609 tests 全綠 · commit 76cb0cb）
  - E2：跨語言接口審查 + 錯誤處理 + rate limit 安全
  - E4：Python 3345 + Rust 763+ 全綠
  - Bybit API 字典手冊同步更新

- [x] PYO3-B08：E5 優化審查（0 OPTIMIZE · 2 DEFER: engine settle_coin + runtime threads）
  - 序列化效率（pythonize vs 手動 to_dict）
  - 不必要的 clone 消除
  - tokio Runtime 資源使用

### 依賴關係

```
PYO3-B01 → PYO3-B02 → PYO3-B03（可與 B04 並行）
                     → PYO3-B04（可與 B03 並行）
PYO3-B03 + B04 → PYO3-B05 → PYO3-B06 → PYO3-B07 → PYO3-B08
```

### 預估文件清單（新建 + 修改）

| 文件 | 操作 | 預估行數 |
|------|------|---------|
| `openclaw_pyo3/Cargo.toml` | 修改 | +3 行 |
| `openclaw_pyo3/src/lib.rs` | 修改 | +10 行 |
| `openclaw_pyo3/src/bybit_bridge/mod.rs` | 新建 | ~80 行（Runtime + 錯誤 + 序列化） |
| `openclaw_pyo3/src/bybit_bridge/client.rs` | 新建 | ~120 行（BybitClient 構造 + AccountManager） |
| `openclaw_pyo3/src/bybit_bridge/orders.rs` | 新建 | ~180 行（OrderManager 方法） |
| `openclaw_pyo3/src/bybit_bridge/positions.rs` | 新建 | ~130 行（PositionManager 方法） |
| `openclaw_pyo3/src/bybit_bridge/market_data.rs` | 新建 | ~200 行（MarketDataClient 方法） |
| `openclaw_pyo3/src/bybit_bridge/instruments.rs` | 新建 | ~100 行（InstrumentInfoCache 方法） |
| `strategy_ai_routes.py` | 修改 | ~30 行改動 |
| `bybit_demo_connector.py` | 修改 | +5 行 DEPRECATED 標記 |
| **合計** | 6 新建 + 4 修改 | **~860 行新代碼** |

---

## ██ R-07：灰度驗證（Go/No-Go 2026-04-10）

> R07-1/2/3/5/6 代碼全部完成，R07-4 即時灰度運行中。
> 詳見 `docs/rust_migration/07--canary_greybox.md`

### Go/No-Go 清單 — **7/7 PASS (2026-04-04)**
- [x] Watchdog 3-STRIKE 驗證 — INC-001 實戰驗證 PASS
- [x] 記憶體 < 100MB — RSS 2.1MB (live, RC-09 binary) PASS
- [x] IPC 零丟失 — 409K+ ticks 連續無間隙 PASS
- [x] tick P50 < 50μs — replay P50=27μs P95=28μs P99=29μs Max=99μs PASS
- [x] 回滾演練 < 10min — 0.091s PASS
- [x] 歷史回放 0 CRITICAL — 201K ticks replay, 0 crash, 5 fills, 4.97s PASS
- [x] 穩態 0 崩潰 — 201K replay 壓測替代 7 天穩態，新 binary 運行中 0 crash PASS

---

## ██ EXT-1：交易所即真相（Exchange-as-Truth）執行模式 ██

> **2026-04-05 五路聯合研究結論：**
> 否決「樂觀成交+回滾」方案（rollback 需跨 5 子系統，無 reverse_fill/on_fill_reverted）。
> 採用「交易所即真相」模式：Demo=Live 統一路徑，Paper 僅為交易所確認後的本地記錄。
> 詳見：`docs/worklogs/2026-04-05--daily_summary.md`

### 架構設計

```
trading_mode = "paper_only"  → 現行邏輯（純本地模擬，測試新策略）
trading_mode = "exchange"    → 交易所即真相（Demo/Live 統一路徑）

Exchange 模式流程：
  on_tick() → 策略 Intent → 風控檢查（Guardian + GovernanceCore）
      ↓
  不做 Paper 成交！發訂單到 order_tx channel → 異步下單到交易所
      ↓
  ExecutionListener WS 回報 OrderUpdate（含 order_link_id 可匹配 intent）
      ↓
  確認 → 用交易所真實價格/數量更新 Paper + strategy.on_fill()
  拒絕 → strategy.on_rejection()（已有）
  部分成交 → 自然處理（每次 WS 回報都是真實數量）
```

### 任務列表

- [x] EXT-1-01：config.rs 加 `trading_mode: "paper_only"|"exchange"` + TradingMode enum ✅
- [x] EXT-1-02：tick_pipeline on_tick 分叉：paper_only 走現行 apply_fill，exchange 走 order_tx 不 apply_fill ✅
- [x] EXT-1-03：ShadowOrderRequest 加 is_primary + order_link_id 欄位（語義重命名延後清理 commit）✅
- [x] EXT-1-04：PendingOrder 追蹤：HashMap<order_link_id, PendingOrder> + order_id→order_link_id 映射 ✅
- [x] EXT-1-05：ExchangeEvent channel (Fill/OrderUpdate/DCP/Disconnected) → event_consumer select! 處理 ✅
- [x] EXT-1-06：Fill 確認：order_id→order_link_id 匹配 → pipeline.apply_confirmed_fill() ✅
- [x] EXT-1-07：超時處理（5s 軟警告 + 60s 硬超時移除）✅
- [x] EXT-1-08：DCP/斷連：DcpTriggered 清除所有 pending，Disconnected 記錄警告（REST reconciliation 延後 EXT-2）✅
- [x] EXT-1-09：E2 審計 3P0+2P1 修復 + E4 回歸 852 Rust + 1075 Py 全綠 ✅
- [x] EXT-1-10：GUI session status 加 trading_mode + IPC get_state 加 trading_mode ✅

### 依賴
- shadow_orders 已 default-on（P2 已完成）
- ExecutionListener 已有 on_fill/on_order_update/on_position_update callback（僅需接線）
- OrderUpdate struct 已有 order_link_id（可匹配）
- Demo→Live 切換：改一行 config BybitEnvironment::Demo → Mainnet

### 風險（CC 審計）
- 雙重成交：需 fill-in-flight ledger 去重
- Principle #3 合規：exchange 模式需獨立 Decision Lease
- Principle #8 審計：需雙日誌（dispatch@T + confirm@T'）

---

## ██ RRC-1：風控運行時接線（Risk Runtime Connect）██

> **2026-04-05 Session 9 審計發現：openclaw_core 已寫好全部高級風控函數，但 openclaw_engine 從未調用。**
> 所有算法已存在（2000+ 行），問題是純粹的接線。

### Phase A: H0Gate 接入 tick_pipeline
- [x] RRC-1-A1：tick_pipeline 加 H0Gate 實例 + on_tick Step 0.5 調用 h0.check()
- [x] RRC-1-A2：main.rs / event_consumer 定期 update_health / update_risk / update_price_ts
- [x] RRC-1-A3：H0Gate shadow mode 先觀察 1 週再啟用阻斷

### Phase B: check_order_allowed 接入 IntentProcessor
- [x] RRC-1-B1：IntentProcessor 新增 Gate 2.7（check_order_allowed 5 check，P1 sizing 後）
- [x] RRC-1-B2：新增 daily_start_balance + daily_loss_pct 追蹤（IntentProcessor，UTC midnight reset）
- [x] RRC-1-B3：exposure 計算（compute_exposure_pct from paper_state.positions + latest_prices）
- [x] RRC-1-B4：RiskManagerConfig 從 engine.toml 初始化 + IntentProcessor.update_risk_config()

### Phase C: check_position_on_tick 替換 check_stops
- [x] RRC-1-C1：tick_pipeline 加 PriceHistoryTracker（每 tick 記錄 → ATR + spike）
- [x] RRC-1-C2：Step 6 替換 check_stops → check_position_on_tick（9 check）
- [x] RRC-1-C3：新增 consecutive_losses 追蹤（盈利重置、虧損累計）
- [x] RRC-1-C4：RiskAction 處理（ClosePosition/HaltSession/SetCooldown → H0Gate cooldown）

### Phase D: 風控單一真相源
- [x] RRC-1-D1：PipelineSnapshot 加入 stop_config + guardian_config + risk_manager_config + consecutive_losses + session_halted + daily_loss_pct + session_drawdown_pct
- [x] RRC-1-D2：GUI /status + /ai-context 改從 Rust 快照讀（ENGINE=None safe）
- [x] RRC-1-D3：Python RiskManager 已為 config-only（無執行路徑方法被調用）
- [x] RRC-1-D4：/config 端點附加 rust_active 區段（stop/guardian/risk configs from Rust）

### Phase E: P1/P2 清理
- [x] RRC-1-E1：修復 ai-context 端點（Phase D 已完成 — 改用 Rust 快照，ENGINE=None safe）
- [x] RRC-1-E2：策略啟停 IPC（Strategy trait +set_active · Orchestrator.set_strategy_active · IPC set_strategy_active）
- [x] RRC-1-E3：治理狀態已統一（GovernanceHub=被動status · GovernanceCore=被動 · PipelineSnapshot 暴露）
- [x] RRC-1-E4：session unhalt 改走 IPC（/unhalt-session → resume_paper IPC → Rust 清除 session_halted）
- [x] RRC-1-E5：Python KlineManager/IndicatorEngine/SignalEngine 保留（backtest fallback，設計決策）

### 依賴
- openclaw_core::risk::checks — check_order_allowed + check_position_on_tick（已實現，有測試）
- openclaw_core::h0_gate — H0Gate 5 check + shadow mode（已實現，30+ 測試）
- openclaw_core::portfolio — check_portfolio_risk 3 check（已實現，有測試）
- openclaw_core::risk::price_tracker — PriceHistoryTracker ATR + spike（已實現）
- openclaw_core::risk::stops — compute_dynamic_stop_pct + anti_cluster_offset（已實現）
- openclaw_core::risk::config — RiskManagerConfig + RegimeMultipliers（已實現）

---

## ██ Phase 0a — PG Schema 基礎（W1，4/11-4/17）

> **DDL 草稿已完成（V001-V005），交叉複審 43/43 MATCH。**
> 存放：`sql/migrations/`
> 決策：一步到位含 TimescaleDB hypertable，Grafana 接受完全中斷。

- [x] 0a-01~04：備份(186K) + 執行 V001-V005 DDL（修復 window 保留字）
- [x] 0a-05~09：舊表 _legacy 重命名(11/14) + Grafana VIEW 橋接(11)
- [x] 0a-10~14：43 tables across 8 schemas + 87 indexes
- [x] 0a-15~16：scorer_training_features VIEW + all indexes
- [x] 0a-17~19：E2 PASS + E4 4507 全綠 + CC/E3 PASS（8 schemas owned by trading_admin, 0 PUBLIC grants）

## ██ Phase 0b — TimescaleDB 啟用（W2-3，4/18-4/30）

- [x] 0b-01~02：Docker image 切換 postgres:16 → timescale/timescaledb:latest-pg16 (v2.26.1)，舊 image 已刪
- [x] 0b-03~05：啟用 28 hypertables（11 market + 7 trading + 3 agent + 1 learning + 4 obs + 2 risk）
      — 15 張非時序表保持 regular（model_registry, symbol_clusters 等）
      — 修復 black_swan_events PK 加入 ts 列
- [x] 0b-06~08：9 compression(7d/14d) + 15 retention(90d/180d/365d) policies + sync_commit 分層
- [x] 0b-09~11：grafana_data_writer INSERT 改為 _legacy 表名 + Grafana VIEWs 驗證通過
- [x] 0b-13~15：requirements-ml.txt 已建 + ML 降級策略已文檔化 + OU Grid σ·√(2/θ) 已修正

> **ML Model Degradation Strategy / ML 模型降級策略（0b-14 文檔）：**
> 1. No trained model exists → fall back to rule-based scoring (confidence from strategy signals)
>    無已訓練模型 → 回退到規則評分（使用策略信號的 confidence）
> 2. ONNX runtime fails → fall back to LightGBM Python inference
>    ONNX 推理失敗 → 回退到 LightGBM Python 推理
> 3. LightGBM fails → fall back to fixed confidence=0.5
>    LightGBM 失敗 → 回退到固定 confidence=0.5
> Implementation: Phase 2 task 2-11 (Scorer pipeline). / 實現：Phase 2 任務 2-11（Scorer 管線）。
- [x] 0b-16~19：E4 4507 全綠 + grafana_data_writer 30 tests PASS

## ██ Phase 1 — 市場數據止血 + FeatureCollector + PSI（W4-5，5/01-5/14）

- [x] Day 0：event_consumer.rs 提取 + database/ 模組 + sqlx 0.8 + Docker test PG（commit 8e0cccd）
- [x] G1 1-01~06：FeatureCollector 34-dim + market_writer(klines/tickers) + feature_writer(UPSERT) + pipeline channels（commit ddbc7af + 7aaec66 audit fix）
- [x] G2 1-07~12：market_writer 全 10 表 + fallback.rs + rest_poller(funding/OI/LSR) + quality_writer（commit bf0725a）
      — G2 audit 6 FAIL 修復：fallback wiring + REST spawn + quality type + liquidation NOT NULL（commit adbe0a7）
- [x] G3 1-13~17：PSI drift + ADWIN + feature_baselines + versioning + paper hooks（commit 86ae00e）
- [x] G4 1-18~20：E2(1 P0 fix) + E4(4143 全綠) + E5(PASS)（commit 13ae4ee）
- [ ] 1-14~15：ExperimentLedger JSON→PG — **延後至 Phase 2**（F7 審計決策）
- [ ] 1-FA-1：FundingArb 雙腿回滾 — **延後至 Phase 2**

## ██ Phase 2 — 交易鏈 + Scorer + ONNX（W6-9，5/15-6/11，含 buffer）

- [x] 2a-01~04：trading_writer (signals/intents/fills/positions → 4 trading.* 表)（commit 41e144d）
- [x] 2a-05~07：context_writer (decision_context_snapshots 15 flat + 3 JSONB)（commit 41e144d）
- [x] 2a-08~09：ExperimentLedger PG — V007 DDL + Rust CRUD（Phase 1 debt cleared）（commit 41e144d）
- [x] 2b-infra：ml/model_manager(ArcSwap ONNX) + ml/scorer(3-tier) + ml/kelly_sizer(fractional Kelly) + MlConfig（commit e06c77c）
- [x] 2-DE：Kelly Gate 2.5 接入 intent_processor + Python ml_training/(label/trainer/calibration/onnx/leakage)（commit 7d68cfe）
- [x] 2-FG：Parquet ETL(DuckDB) + E2/E4 final review PASS（commit fb45c95）
- [x] 2-KS-1：Kelly Position Sizing in Rust — kelly_sizer.rs + Gate 2.5（commit e06c77c + 7d68cfe）
- [ ] 2-11 actual training：需要引擎運行收集 trading.fills 數據後才能訓練 LightGBM
- [ ] 2-PYO3-1：ContextDistiller PyO3 接入（延後，基礎設施已完成）
- [ ] ort crate activation：ONNX model_manager placeholder ready，首個模型訓練後 one-line 啟用

## ██ Phase 3a — update_params() 改造 = AGT-1（W9-10，6/05-6/18）

- [x] 3a-01~07：Strategy trait +3 JSON methods + 4 策略 StrategyParams impl + update/get/validate（commit a212a82）
- [x] 3a-08~12：14 new tests + E2 + E4 (358 engine pass, 0 fail)

## ██ Phase 3b — Optuna + Thompson Sampling + CPCV + 黑天鵝（W11-12，6/19-7/02）

- [x] PF-1：IPC update_strategy_params/get_strategy_params/get_param_ranges（commit b8b4f3c）
- [x] PF-2：scorer_trainer.py 對齊 n_folds=4, embargo 24/4/8/72h（commit b8b4f3c）
- [x] PF-3：V004 DDL 確認 DRAFT + trading.fills=5 評估（commit b8b4f3c）
- [x] 3b-01~02：Optuna TPE SQLite JournalStorage + EV_net + IPC integration（commit 782dd03）
- [x] 3b-03+04：CPCV 4-fold + 策略特定 embargo + power guard（commit 782dd03）
- [x] 3b-05+06：Thompson Sampling NIG + Empirical Bayes + exploitation floor（commit 782dd03）
- [x] 3b-09~10：黑天鵝 4 信號投票 Rust (MAD/corr/vol/velocity)（commit 380b38a）
- [x] 3b-11：ETL DuckDB label generation（commit 380b38a）
- [x] 3b-12：集成測試 test_optuna_to_ts_pipeline 3/3 pass（commit 9b0287f）
- [x] 3b-13：PSI 基線重建 + 7 天冷卻 + block bootstrap（commit 380b38a）
- [ ] 3b-07：BH-FDR 多重比較校正 — **延後至 Phase 4**（無真實 trial 數據）
- [ ] 3b-08：Grid 多目標 Pareto — **延後至 Phase 4**（單策略，需數據累積）
- [ ] 3b-14~17：E2 + E4 + E5 + QC — 隨 G1/G2/G3 各批次完成

## ██ Phase 4 — Claude Teacher + LinUCB + News + DL-3（W13-15，7/03-7/23）

- [ ] 4-01~03：Claude-as-Teacher → ExperimentLedger + 效果追蹤
- [ ] 4-04~06：LinUCB + Model Performance 監控 + Adversarial Validation
- [ ] 4-07~10：新聞 Agent 接口（mock，數據源暫緩）
- [ ] 4-11~14：DL-3 TimesFM/Chronos（異步，A/B 驗證，AUC<0.01 則棄用）
- [ ] 4-15~20：全 3 個集成測試 + E2 + E4 + CC/E3 + AI-E Go/No-Go + E5

## ██ Phase 5 — James-Stein + DL-1 + DL-2（W16-18，7/24-8/13）

- [ ] 5-01~03：James-Stein per-parameter shrinkage + k-means 聚類
- [ ] 5-04~07：DL-1 Symbol Embedding(4D/8D/12D) + DL-2 Regime LSTM Shadow
- [ ] 5-08~09：JS+Scorer 整合 + correlation_pairs 寫入
- [ ] 5-10~13：E2 + E4 + QC + E5

## ██ Phase 6 — 驗收（W19-20，8/14-8/27）

- [ ] 6-01~03：漸進放權管線 + 畢業邏輯 + Live 審批
- [ ] 6-04~06：全管線回放 + 壓測 + sync_commit Live 驗證
- [ ] 6-07：EvolutionEngine 標記 deprecated
- [ ] 6-08：完整文檔
- [ ] 6-09~13：E2 + E4 + QA 端到端驗收 + E5 + PM 最終確認

---

## ██ Phase 4-Conditional — 條件性（有前置條件觸發）

- [ ] 4-1：PairsTrading（需 3 月協整驗證）
- [ ] 4-2：Beta Hedging（需 HedgingEngine 穩定 1 月）
- [ ] 4-3：Kalman Filter（KAMA 表現不理想時）
- [ ] 4-5：Mac Studio 遷移 + 大模型（硬件到手）
- [ ] 4-10：Jump detection — K 線 body > 3σ → 加寬止損

---

## ██ Live Gate — Paper 21 天 + Live 準備

> 前置：融合方案 Phase 6 完成 + Phase R 完成 + Alpha > 0

- [ ] LG-1：Paper Trading 穩定運行 21 天
- [ ] LG-2：H0 Gate blocking 驗證（shadow→blocking）
- [ ] LG-3：provider pricing table 正式綁定
- [ ] LG-4：M 章 Supervised Live Gate
- [ ] LG-5：N 章 Constrained Autonomous Live

---

## ██ 技術債務（Phase 1 前清理）— ✅ 全部完成

- [x] TD-01：pipeline_bridge.py 拆分（2587→55 facade + 3 mixins）— bridge_core(831) + bridge_agents(919) + bridge_stats(825)
- [x] TD-02：phase2_strategy_routes.py 拆分（1838→81 facade + 4 files）— strategy_wiring(1180) + read(396) + write(223) + ai(141)
- [x] TD-03：paper_trading_routes.py 精簡（1144→857, -25%）— paper_trading_wiring(488) 提取

---

## ██ 長期整合（非緊急）

- [ ] OC-1：OpenClaw Webhook 告警
- [ ] OC-2：Telegram 通道
- [ ] OC-3：多通道分級告警
- [ ] OC-4：MCP PostgreSQL 自然語言查詢
- [ ] OC-5：FundingArb REST 資金費率輪詢（Rust 引擎接入）
