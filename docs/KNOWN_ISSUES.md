# Known Issues & Unverified Risks
# 已知問題與未驗證風險
#
# 用途：記錄已識別但尚未修復/驗證的問題，供每次 session 接手時排查參考。
# Purpose: Track identified but unresolved/unverified issues for troubleshooting reference.
#
# 格式：每個問題獨立章節，含 狀態/位置/排查方式/緩解方案。
# 狀態：OPEN（待驗證）/ CONFIRMED（已確認是問題）/ RESOLVED（已修復，附 commit）
#
# 統計：OPEN 14 / CONFIRMED 0 / RESOLVED 25
# 最後更新：2026-05-16（Wave 1 12-agent audit closure + 多 healthcheck/governance event reconcile）
#
# 2026-05-16 reconcile 範圍：
# - W-C MAG-082 Stage 2 WINDOW_PASS（2026-05-11）已關
# - W-D MAG-083 三角 audit + MAG-084 operator sign-off（2026-05-11）已關
# - W-AUDIT-3b RouterLeaseGuard runtime smoke（2026-05-15）已關
# - `[55]` fill-lineage source-cleared（2026-05-15）已關
# - `[27]` intents counter freeze post-grace closure（2026-05-15）已關
# - `[67]` feature baseline restored（2026-05-15）已關
# - W-AUDIT-5a/5b ops 對賬（2026-05-15）已關
# - W-AUDIT-7c GUI lexical scope shadow fix（2026-05-15）已關
# - W-AUDIT-8a Phase C0 liquidation inventory source/doc 已關（C1 24h proof 跑中）
# - A4-C BTC→Alt Lead-Lag 從 promotion 路徑歸檔（2026-05-15）
# - V079 / V083 / V084 schema 已 apply（2026-05-15 之前）
# - strategy_trial_ledger schema 已 apply（2026-05-15 之前）
# - 12-agent audit Wave 1 land（2026-05-16，commit cabb2fcd + 88f9254f）
# - 12-agent audit Wave 2 land（2026-05-16，commit ef6ea79f + 5682994c + 27f02a07）— WP-03 OU sigma + WP-04 AI obs + WP-07 dead code audit + WP-10 Bybit 110017 + BB-MF-3 cooldown split
# - 12-agent audit Wave 3 land（2026-05-16，commit f31b6e8f + 05756ae3）— WP-06 deepcopy 3→2 + WP-08 engine_mode + purge_days + WP-13 demo reconciler slot
# - 12-agent audit Wave 4 Phase 1 land（2026-05-16，commit 564c9db6 + fca27914）— WP-11 15 failing Python tests fix (16→1 flaky) + WP-12 DEFERRED
# - Wave 3a re-review consolidation: spec v1.3 + AMD-2026-05-15-02 v0.4（commit c0d34fcb + 2f55d053）
# - Wave 2a Track A2 V094 schema migration spec finalize（commit 9b1117a0）
# - Wave 3b BB1 6 dictionary updates land（commit 28c571c7）
# - BB 字典 §4.2 110017 ReduceOnlyReject row 補（commit 564c9db6 順手 land）
# - tab-learning.html ocExplain 區段繁化（commit 564c9db6 順手 land）
# - PA reconcile: MIT-P0-2 「6/12 ML cron 未裝」= FALSE FINDING（廣口徑定義漂移；真實 10 active cron 已裝）
# - 新加 OPEN：P0-EDGE-1 / P0-LG-1/2/3 / P0-OPS-1..4 / W-AUDIT-8a C1 / W-AUDIT-8b Stage 0R
# - 新加 OPEN（Wave 2-4 deploy gap）：Rust binary 仍 `7b33ab2e` 未 rebuild，Wave 2-4 source IMPL DONE / NOT DEPLOYED
# - 新加 OPEN（Wave 2-4 P1/P2 follow-up）：P1-BBMF-WIRING-1（commands.rs / dispatch.rs production wiring）/ P1-WP13-LEFTOVER-1（main.rs:822 + 1372 by-value cmd_tx）/ P2-WP05-FUP-1（32 處 str(exc) 殘留）/ P2-COMMON-JS-LOC / P2-CROSSTAB-I18N / P2-STOCHASTIC-LEAK / P2-PA-CALLPATH-GREP-RULE / P2-CRON-DELIBERATE-NOT-INSTALLED-LIST（6 個 deliberate 未裝 cron list）
# - 新加 OPEN（Wave 2-4 待 operator 拍板）：WP-04 budget 100→2 post-hoc ratification / WP-03 walk-forward backtest 或 deploy-gate / engine --rebuild 部署窗口 / Race protocol SOP

---

# ━━━ Rust Engine（R-05 Soak Test 排查項）━━━

## RESOLVED — RE-1：Rust Engine 長期記憶體洩漏風險

**來源**：R-05 決策（2026-04-03），10 分鐘實測無法覆蓋
**嚴重性**：LOW（降級：原始描述已過時）
**修復**：2026-04-05 審計確認無洩漏風險
**審計結果**：
- `fills: Vec<PaperFill>` — **不存在**。原始描述基於舊版代碼。目前 fills 存於 tick_pipeline 的 `recent_fills: VecDeque`，已有 cap=50。
- `positions` HashMap — 只在 `apply_fill()` 插入，`close_position()` 移除。自然有界（最多 25 symbols）。
- `latest_prices` / `latest_turnovers` / `api_unrealized_pnl` — symbol-keyed HashMap，overwrite-on-insert，自然有界（≤ SYMBOLS.len() = 5）。
- tick_pipeline 的 `recent_signals`(100), `recent_intents`(50), `recent_fills`(50), `adl_alerts`(50) — 全部 VecDeque 且有 pop_front 上限。
- KlineBuffer — capacity=500, `append()` 時 evict oldest。
- `persistence.rs` JSONL — 磁碟增長，非記憶體。保持監控。
**結論**：Go/No-Go replay 確認 RSS 2.1MB（201K ticks），無增長趨勢。

---

## RESOLVED — RE-2：WS 24h 強制斷線無自動重連

**來源**：R-05 決策（2026-04-03）
**嚴重性**：原 HIGH → 已修復
**修復**：2026-04-05
**審計結果**：
- ws_client.rs `run()` 已有 exponential backoff reconnect 循環（base_delay * 2^attempt, cap 60s）
- bybit_private_ws.rs `run()` 同樣已有重連循環
- 24h 斷線場景：server close frame → break inner loop → 自動重連。已正確處理。
**修復內容（RE-2 fix）**：
1. `ws_client.rs`：`process_message()` 返回 bool，event channel 關閉時回傳 false → `run()` 不再空轉
2. `main.rs`：公共 WS + 私有 WS 均加入 supervisor 包裝 — task 意外退出時自動重建 + 退避重啟
3. Supervisor 退避：5s * 2^attempt, cap 60s

---

## OPEN — RE-3：跨 UTC 日切邊界行為未驗證

**來源**：R-05 決策（2026-04-03）
**嚴重性**：LOW（降級：2026-04-05 審計）
**背景**：Bybit kline 以 UTC 00:00 為日切界，日切瞬間可能出現：
- 1D kline confirm=true 收盤 candle 觸發大量策略信號
- funding rate settlement（每 8h，00:00 是其中之一）
- 瞬間 spread 擴大 / 流動性下降
**位置**：策略的 kline 消費邏輯（MA/BB 使用日線窗口時）
**2026-04-05 審計補充**：
- ws_client.rs 已有 confirmed-only kline 過濾（3 個 unit test 覆蓋）
- 所有 6 策略均有 per-strategy cooldown（MA: 5min, FundingArb: 1h 等）
- cooldown 為絕對毫秒差值，非日曆感知 — 理論上日切信號仍可能在 cooldown 窗口外重複觸發
- 風險實際較低：使用 1D 策略的場景極少，且 cooldown 提供基本保護
**排查方式**：Phase 1 soak test 跨越 UTC 00:00 觀察
**建議**：Phase 3b 策略參數 DB 持久化時考慮加入 `min_hours_between_1d_entries` 可選參數

---

# ━━━ 架構 / 管線問題 ━━━

## RESOLVED — ARCH-1：MessageBus Guardian→Executor 路徑未打通

**來源**：PA 技術審查（2026-04-01）
**嚴重性**：原 HIGH → 降級 LOW（架構已完整，待激活）
**修復**：2026-04-05 審計 + intent_id dedup 安全網
**審計結果**：
- **MessageBus 路徑已完整實現**：Strategist._produce_intents() → bus.send(TRADE_INTENT) →
  Guardian._handle_trade_intent() → review_intent() → bus.send(APPROVED_INTENT) →
  Executor._handle_approved_intent() → execute_order() → bus.send(EXECUTION_REPORT)
- 當前兩條路徑互斥：pipeline_bridge 直接調用 vs MessageBus 路由。未同時啟用。
- **ARCH-1 fix**：ExecutorAgent 新增 intent_id 去重（OrderedDict + 10s 窗口），防止雙路徑同時激活時重複執行。
- **激活決策**：延後至 Phase 3a+，需配合測試驗證。當前 pipeline_bridge 路徑運行穩定。

---

## RESOLVED — ARCH-2：Pipeline Bridge GovernanceHub 注入時序風險

**來源**：PA 審查（2026-03-31）
**嚴重性**：原 MEDIUM → 已修復
**修復**：2026-04-10 DEAD-PY-2 Phase A 全面移除 PipelineBridge（4 bridge 文件全刪）
**問題**：PipelineBridge 在 `phase2_strategy_routes.py` 注入 GOV_HUB 之前就已創建
**結論**：DEAD-PY-2 刪除了所有 Python 交易邏輯，PipelineBridge 已不存在。問題自動解決。

---

## OPEN — ARCH-3：TruthSourceRegistry + ExperimentLedger 持久化不完整

**來源**：PA 技術審查（2026-04-01）
**嚴重性**：MEDIUM
**問題**：ExperimentLedger 有 `save_snapshot()` / `load_snapshot()` 實現，但生產代碼中 `save_snapshot()` 的自動定期調用尚未確認接通。系統重啟可能丟失累積的學習數據。
**位置**：`app/experiment_ledger.py`、`app/experiment_routes.py`
**影響**：重啟後 ExperimentLedger 的假設數據可能丟失
**排查方式**：確認 `save_snapshot()` 是否在 shutdown hook 或定期任務中被調用

---

## RESOLVED — ARCH-4：Dependency Injection Silent Fail-Open 模式

**來源**：PA 審查（2026-03-31）
**嚴重性**：原 MEDIUM → 已修復
**修復**：2026-04-05
**改動**：
- bridge_agents.py H0 Gate：exception handler 從 fail-open 改為 fail-closed（return None + 計數 + 標記）
- bridge_agents.py Cost Gate：exception handler 從 fail-open 改為 fail-closed（return None + 計數 + 標記）
- bridge_core.py Governance Lease：已是 fail-closed（無需改動）
- Guardian review_intent()：已是 fail-closed（any error → REJECTED）
- 剩餘 `if self._xxx:` 模式為 advisory/optional 組件（telegram/audit/learning weight），fail-open 是正確行為

---

# ━━━ 交易邏輯問題 ━━━

## OPEN — TRADE-1：Strategy Alpha 未經統計驗證

**來源**：改善報告 V3 Final（2026-04-03）
**嚴重性**：HIGH（業務風險，非代碼缺陷）
**問題**：所有 5 個策略使用標準 TA 指標，無統計 edge 驗證。Paper 交易 4 週顯示負淨 PnL。
**影響**：live 交易可能持續虧損
**緩解**：Alpha 基準測試並行進行中（Phase 0 Day 1 開始 2 週 Paper）

---

## RESOLVED — TRADE-2：Intent 排隊競態條件

**來源**：改善報告 V3 Final（2026-04-03）
**嚴重性**：MEDIUM
**問題**：Normal channel 推送 long intent + 閃崩觸發 fast-lane close_all。若 Guardian 先處理 long（approved → 開倉），再處理 close_all（平倉），雙重手續費浪費。
**原位置**：`app/pipeline_bridge.py` intent 隊列（已於 DEAD-PY-2 Phase A 刪除）
**修復**：Rust `on_tick()` 同步處理——fast_track 在 tick 頂部（L80-155）先於策略 intent（L500+）執行，`ft_pause_new_entries` 旗標阻止同 tick 內新開倉。無異步隊列，無競態。（2026-04-12 審計確認）

---

## RESOLVED — TRADE-3：Kelly 計算偏差 — 未實現 PnL 未計入勝率

**來源**：改善報告 V3 Final（2026-04-03）
**嚴重性**：MEDIUM
**問題**：`win_rate` 和 `avg_win/avg_loss` 只算已平倉交易。未平倉虧損倉位被排除 → 勝率虛高 → Kelly fraction 過於激進
**位置**：`position_sizer.py` Kelly 計算
**修復**：新增 `unrealized_pnl` 參數，負值時 dampening=max(0.5, 1-|pnl|/balance)（2026-04-03）

---

## RESOLVED — TRADE-4：Partial Fill 回滾數量不一致

**來源**：改善報告 V3 Final（2026-04-03）
**嚴重性**：MEDIUM
**問題**：限價單部分成交（下 0.1 BTC，成交 0.06），回滾時應平 0.06 而非 0.1 → 倉位大小錯誤
**原位置**：`app/paper_trading_engine.py` + `app/oms_state_machine.py`（已於 DEAD-PY-2 Phase B/C 刪除）
**修復**：Rust 架構無此問題——每筆交易所成交（`event_consumer/mod.rs` L589）獨立攜帶 `exec_qty`，`paper_state.apply_fill()` 僅使用傳入的實際成交量（非原始訂單量）；`reduce_position()` 中 `actual_reduce = reduce_qty.min(pos.qty)` 保證不會超額平倉。無"回滾"概念，每筆 fill 獨立結算。（2026-04-12 審計確認）

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

## RESOLVED — TEST-1：4 個 multi_interval_ws 測試失敗

**來源**：2026-04-05 Session 7，外部 linter 變更引入
**嚴重性**：MEDIUM
**問題**：multi_interval_ws 模組的 4 個測試（test_empty_intervals, test_full_subscription_list, test_extended_subscription_list, test_multi_symbol_subscriptions）因 linter 對 subscription 邏輯的修改而失敗。非本 session 代碼變更。
**位置**：`rust/openclaw_engine/src/multi_interval_ws.rs`
**影響**：WS 訂閱功能可能受影響（生產環境未驗證）
**排查方式**：`cargo test -p openclaw_engine --lib multi_interval_ws`
**緩解**：需要檢查 linter 的具體修改並修復測試或代碼

---

## OPEN — DEBT-2：main.rs 超過 800 行警告線

**來源**：2026-04-05 Phase 1+2 累積
**嚴重性**：LOW
**問題**：main.rs 因 DB pool + 6 個 writer task spawn + REST poller + quality monitor + drift detector + feature version init 累積至 ~920 行，超過 800 行警告線
**位置**：`rust/openclaw_engine/src/main.rs`
**緩解**：提取 DB 初始化邏輯到 `database/init.rs` helper 函數。不阻塞功能。

---

## OPEN — ML-1：ort crate 未啟用（ONNX 推理為 placeholder）

**來源**：2026-04-05 Phase 2b-infra 設計決策
**嚴重性**：LOW（設計如此，非缺陷）
**問題**：model_manager.rs 的 predict() 返回 None（placeholder），因為 ort crate 未添加（避免 ~200MB 下載）。Scorer 正確降級到 Tier 2 rule-based。
**位置**：`rust/openclaw_engine/src/ml/model_manager.rs:107`
**緩解**：首個 ONNX 模型訓練完成後，添加 ort crate 並替換 placeholder。One-line change。

---

## OPEN — ML-2：ml_training 測試需要 numpy/ML 依賴

**來源**：2026-04-05 Phase 2 Batch E
**嚴重性**：LOW
**問題**：label_generator 等測試需要 numpy/lightgbm/scikit-learn（requirements-ml.txt），基礎環境無這些包。leakage_check 測試可在基礎環境運行。
**位置**：`program_code/ml_training/tests/test_label_generator.py`
**緩解**：使用 `pip install -r requirements-ml.txt` 安裝 ML 依賴後運行。CI 需要獨立的 ML test stage。

---

## OPEN — DEBT-1：legacy_routes.py 1276 行超出 1200 行硬上限

**來源**：重構日誌（2026-04-01）
**嚴重性**：LOW
**問題**：文件超出 CLAUDE.md §九 規定的 1200 行硬上限
**位置**：`app/legacy_routes.py`（1276 行）
**阻塞**：拆分需改變 `register_legacy_routes(app)` 模式，中等風險
**備註**：架構技術債，不影響功能

---

## RESOLVED — RISK-1：GUI 風控參數未傳遞到 Rust 引擎

**來源**：Session 8 架構審查
**嚴重性**：原 HIGH → 已修復
**修復**：2026-04-05 Session 9（commits f7c9086~d053a51）
**問題**：GUI 上調整的風控參數（Hard Stop、Take Profit、Trailing Stop 等）僅停留在 Python 層，不影響 Rust 引擎的實際風控行為。
**修復內容**：
- PaperSessionCommand::UpdateRiskConfig IPC 命令（9 欄位）
- Python ipc_client.update_risk_config() + risk_routes.py 接入
- Guardian expose config()/update_config() 供運行時更新
- StopConfig +take_profit_pct + check_take_profit()
- RuntimeConfig +max_leverage, max_drawdown_pct, max_same_direction_positions
- engine.toml → Guardian + StopConfig + IntentProcessor 啟動接線
- Agent auto-tuning：/api/risk/agent-adjust → IPC → Rust engine

---

## OPEN — RISK-2：Sharpe 動態倉位調整未實現

**來源**：Session 9 審查
**嚴重性**：LOW（設計如此，非缺陷）
**問題**：kelly_sizer.rs 有 fractional Kelly 實現，但 Sharpe-based 動態 position sizing 尚為 placeholder。當前使用固定 fractional Kelly + ATR vol-adjust。
**位置**：`rust/openclaw_engine/src/ml/kelly_sizer.rs`
**緩解**：Phase 4 ML pipeline 訓練完成後可加入 Sharpe ratio 作為 sizing 輸入。不阻塞當前功能。

---

## RESOLVED — RISK-3：Daily Loss Limit 僅 Python 層執行

**來源**：Session 9 架構審查
**嚴重性**：原 MEDIUM → 已修復
**修復**：RRC-1 + position_risk_evaluator 實現 Rust 日損限額
**問題**：原先日虧損限額僅在 Python GovernanceHub SM-04 中執行
**修復內容**：IntentProcessor.daily_loss_pct_pub() + position_risk_evaluator.evaluate_positions()
   的 daily_loss 參數 → RiskConfig.limits.max_daily_loss_pct 比對 → CloseAll + HaltSession。
   Rust 引擎獨立執行，不依賴 Python。

---

## RESOLVED — DATA-1：trading.fills realized_pnl 永遠為 0

**來源**：Session 9c 運營排查（2026-04-05）
**嚴重性**：HIGH
**修復**：`paper_state.rs` apply_fill() 改為返回 f64 PnL，tick_pipeline 兩條路徑（paper + exchange）使用返回值寫入 DB
**根因**：TradingMsg::Fill 構造時硬編碼 `realized_pnl: 0.0`，apply_fill() 計算了 PnL 但無返回值
**commit**：本次 commit

---

## RESOLVED — GATE-1：Gate 3 Cost Gate 未實現（只有註釋佔位）

**來源**：Session 9c QC 分析（2026-04-05）
**嚴重性**：HIGH（導致策略在低波動市場盲目下單，36 筆全虧手續費）
**修復**：`intent_processor.rs` 實現 Gate 3 — QC 公式：ATR×confidence×qty < 1.5×round_trip_fee → 拒絕
**常數**：min_confidence=0.15, k_paper=1.5, k_live=2.0, ATR 不可用時 fail-open
**後續**：策略 confidence 需從固定 0.50 改為動態設置（當前全被攔截）
**commit**：本次 commit

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

---

# ━━━ 2026-05-16 Wave 1 12-agent audit reconcile — RESOLVED ━━━

## RESOLVED — WC-MAG-082：W-C MAG-082 Stage 2 24h Canary Validation

**來源**：Sprint N+1 Wave W-C 收口
**嚴重性**：原 HIGH（live promotion gate） → 已關
**修復**：2026-05-11 WINDOW_PASS（`docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md`）
**驗證**：Decision Lease router gate evidence-mode 在 `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` + `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow` 下完成 24h 觀察 + lineage 寫入 Agent Spine ExecutionPlan rows
**註**：本關閉 = MAG-082 stage 2 evidence collection done，**非** true-live auth、**非** Executor order authority。

---

## RESOLVED — WD-MAG-083：W-D MAG-083 Final Release Audit

**來源**：Sprint N+1 Wave W-D
**嚴重性**：MEDIUM
**修復**：2026-05-11 三角 audit done（PA + QC + MIT 並行獨立 review；`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w_d_mag083_pa_audit.md`）

---

## RESOLVED — WD-MAG-084：W-D MAG-084 Operator Sign-Off

**來源**：Sprint N+1 Wave W-D
**嚴重性**：MEDIUM
**修復**：2026-05-11 operator sign-off（`docs/governance_dev/2026-05-11--w_d_mag084_signoff.md`）

---

## RESOLVED — WA-3b：W-AUDIT-3b RouterLeaseGuard runtime smoke test

**來源**：12-agent audit Wave W-AUDIT-3b
**嚴重性**：HIGH（runtime governance gate）
**修復**：2026-05-15 runtime smoke pass（`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_audit_3b_runtime_smoke.md`）

---

## RESOLVED — HC-55：`[55]` fill-lineage healthcheck invariant 漂移

**來源**：Sprint N+1 P1 healthcheck audit
**嚴重性**：HIGH（healthcheck 誤判導致 micro-canary 假警）
**修復**：2026-05-15 P1-HEALTHCHECK-55-INVARIANT 將 50%-of-all-chains heuristic 改為 fully-filled plan invariant
**驗證**：trade-core PG 直查 144 chains / 25 fully-filled / 25 真 fill ER；`partial_plan_fill_chains=13` 另列；bad quality counters 0
**註**：partial per-fill ER 仍是 future hardening scope，不是 Stage 1 demo blocker。

---

## RESOLVED — HC-27：`[27]` intents counter freeze post-grace closure

**來源**：Sprint N+1 P1 healthcheck audit
**嚴重性**：HIGH
**修復**：2026-05-15 18:12 UTC 直接 narrow probe PASS（demo stale=3.4m / 30min_n=4 / live_demo + live 在 30m 內 0 intents 為 demo-shadow expected）
**註**：Stage 1 demo 仍被 alpha gates blocked，不是 `[27]` blocker。

---

## RESOLVED — HC-67：`[67]` feature baseline readiness 0 active rows

**來源**：W-AUDIT-4b feature baseline writer audit
**嚴重性**：HIGH（feature drift detector 失效）
**修復**：2026-05-15 13:13 UTC `feature_baseline_writer_cron.sh` apply 還原 `observability.feature_baselines` 至 `active_rows=646` / `active_symbols=19` / `feature_names=34/34`
**註**：drift events 仍等 configured burn-in，不是 [67] blocker。

---

## RESOLVED — WA-5a/5b：W-AUDIT-5a/5b ops 對賬 closure

**來源**：12-agent audit Wave W-AUDIT-5
**嚴重性**：MEDIUM
**修復**：2026-05-15 ops 對賬 walk-through pass

---

## RESOLVED — WA-7c：W-AUDIT-7c GUI lexical scope shadow

**來源**：12-agent audit Wave W-AUDIT-7c
**嚴重性**：HIGH（governance-tab.js prod SyntaxError）
**修復**：2026-05-15 3-pass round + node --check SOP 落地（feedback_gui_node_check_sop）；A3 + E2 + 主邏輯三方獨立 catch 救 prod GUI

---

## RESOLVED — WA-8a-C0：W-AUDIT-8a Phase C0 liquidation revival inventory

**來源**：12-agent audit Wave W-AUDIT-8a Phase C
**嚴重性**：MEDIUM
**修復**：2026-05-15 source/doc closed — `market.liquidations` table 存在 / 0 rows / production topic builders guarded against `liquidation.*` 等 / 60s smoke `SMOKE_PASS_NOT_C1_PROOF`
**註**：C1 24h isolated `allLiquidation.BTCUSDT` proof 仍在 trade-core PID `4100789` 跑中（since 2026-05-15T19:53:09Z），未通過 BB + MIT sign-off 前禁開 production 訂閱。

---

## RESOLVED — A4C-ARCHIVE：A4-C BTC→Alt Lead-Lag from promotion path

**來源**：Sprint N+1 W2 A4-C IMPL + Stage 0R replay
**嚴重性**：HIGH（promotion candidate）
**修復**：2026-05-15 PM/FA verdict — A4-C 從 promotion 路徑歸檔；`P1-A4C-RCA-1` no-revive（`avg_net_bps=-1.0013` / `PSR(0)=0.1904` / `DSR=0` / R²(120)=0）；finite X=5/Y=0.20 probe 也僅 +1.4739 bps
**註**：不開 `P1-A4C-REV-1`；不重跑同樣 BTC-return/xcorr feature shape；panel/producer 留 diagnostic-only。

---

## RESOLVED — V079：strategy_trial_ledger schema apply

**來源**：AMD-2026-05-09-04 Demo→LivePending promotion_evidence producer
**嚴重性**：MEDIUM
**修復**：V079 schema applied（migration runner + linux pg verify done）

---

## RESOLVED — V083/V084：post Wave 1 migration apply

**來源**：Sprint N+0 P2 closure packet
**嚴重性**：MEDIUM
**修復**：V083 / V084 dry-run apply 2026-05-10；V083 IPC close fix 已 land；fee source dual-source schema applied。

---

# ━━━ 2026-05-16 12-agent audit Wave 1 reconcile — OPEN ━━━

## OPEN — P0-EDGE-1：5 textbook 策略 negative realized edge

**來源**：W-AUDIT P0-EDGE-1 + 2026-05-15 full healthcheck `[40]` 仍 WARN
**嚴重性**：P0 BLOCKER（live promotion 全鏈封死直到至少 1 個策略 cohort 轉正）
**位置**：5 textbook strategies (`ma_crossover` / `bb_breakout` / `bb_reversion` / `grid_trading` / `funding_arb`) demo edge 全 negative
**狀態**：Alpha Surface C1（liquidation revival）/ C1 24h proof / W-AUDIT-8b funding skew Stage 0R replay 待跑；A4-C 已 archive；其他 alpha candidate spec phase
**緩解**：W-AUDIT-8a/8b/8c 並行 prep；replay-first validation default；無 alpha gates 轉正前 paper/demo promotion 路徑全 freeze

---

## OPEN — P0-LG-1：H0 production caller IMPL pending

**來源**：Live Gate LG-1 prerequisites
**嚴重性**：P0（true-live blocker）
**位置**：`rust/openclaw_engine/src/h0_gate/`（H0 本地判斷內核）
**問題**：H0 Gate 雖然在 shadow mode 運行，但 production caller 在進入 LG-1 supervised-live 前必須 IMPL（fail-closed 路徑 + telemetry binding）
**狀態**：spec phase；E1 派工待 alpha gates 轉正後啟動

---

## OPEN — P0-LG-2：provider pricing binding IMPL pending

**來源**：Live Gate LG-2 prerequisites
**嚴重性**：P0（true-live blocker）
**位置**：FeeSource 雙源（Bybit API / DemoConservativeDefault / ColdDefault）+ RiskConfig pricing binding
**問題**：LG-2 T1-T4 spec done（contract tests / startup assertion / FeeSource enum / RiskConfig pricing）；T5+ runtime binding pending alpha gates 轉正
**緩解**：LG-2 IPC slot 已落（`AccountManagerSlot`）；E1/E4 跨 sub-agent 已沒 deploy 卡位

---

## OPEN — P0-LG-3：supervised-live state machine IMPL pending

**來源**：Live Gate LG-3 prerequisites（pricing binding 直接依賴）
**嚴重性**：P0（true-live blocker）
**位置**：governance/state machine + Decision Lease ladder
**狀態**：LG-3 spec v2 final（2026-05-11 PA + QC + MIT 三方 reviewed）；IMPL pending alpha gates

---

## OPEN — P0-OPS-1：HTTPS / secure cookie

**來源**：first-day live ops checklist
**嚴重性**：P0（true-live blocker）
**問題**：Tailscale-internal 已 OK；但 first-day live 需 HTTPS + secure cookie + CSRF + CSP（W-AUDIT-7 E3-LOW-1 CSP unsafe-inline 仍 P2）

---

## OPEN — P0-OPS-2：credential rotation runbook

**來源**：Live ops blocker
**嚴重性**：P0
**問題**：authorization.json / Bybit api_key/secret rotation 程序化 SOP + RTO 仍未驗

---

## OPEN — P0-OPS-3：legal / ToS / geography

**來源**：Live ops blocker
**嚴重性**：P0
**問題**：Bybit ToS / geography restriction / KYC tier / Tax reporting 對齊未完

---

## OPEN — P0-OPS-4：first-day live runbook

**來源**：Live ops blocker
**嚴重性**：P0
**問題**：first-day live 24h staffing + RTO/RPO + emergency liquidate + escalation path runbook 仍未 ratify

---

## OPEN — WA-8a-C1：W-AUDIT-8a Phase C1 24h liquidation topic proof

**來源**：W-AUDIT-8a Phase C 拆分
**嚴重性**：HIGH（alpha candidate prerequisite）
**位置**：`trade-core` PID `4100789`（since 2026-05-15T19:53:09Z）isolated `allLiquidation.BTCUSDT` 24h 訂閱
**狀態**：跑中；24h 報告 + BB + MIT sign-off 後才能解 production revival
**緩解**：production topic 仍 guarded against `liquidation.*` / `price-limit.*` / `adl-notice.*` / `allLiquidation*`；本 probe 不能進 production topic builder

---

## OPEN — WA-8b：W-AUDIT-8b Funding Skew Directional Stage 0R replay packet

**來源**：12-agent audit Wave W-AUDIT-8b
**嚴重性**：HIGH（alpha candidate）
**狀態**：spec v0.2 CONDITIONAL DESIGN APPROVED 2026-05-15（QC + MIT + BB 三方）；read-only Stage 0R replay query/report packet 待 PA / E1 派
**約束**：30m primary horizon / branch-separated（crowded-long fade + crowded-short squeeze）/ `K_total >= K_prior+4050` / `DSR>=0.95` / PBO fail-closed / raw panel as-of joins / funding attribution `excluded`

