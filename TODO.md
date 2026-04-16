# OpenClaw TODO — 工作計劃清單

**最後更新：2026-04-16**（P0-0 RECONCILER-BURST-FIX ✅ startup grace window 修復 + 6 新單元測試）

**測試基準線**：Rust **engine lib 1336 (ort) / 1330 (default) + core 380 + e2e 35 + reconciler_e2e 18 + ort integration 5** · Python **2883 passed (5 skipped · 0 fail)** · ml_training **182 passed (10 skipped)**

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> 條目分級：**P0 阻塞關鍵路徑** → **P1 當週活躍** → **P2 下週排期** → **P3 長期專項** → **P4 Backlog / Conditional**
> 歷史歸檔索引在文件末尾。已完成里程碑視角見 README.md 與 CLAUDE.md §三。

---

## 🎯 啟動時必做檢查

### 引擎健康三連（每 session 開頭）

```bash
# 1. 引擎存活 + canary 記錄 + 崩潰數
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status
systemctl --user status openclaw-watchdog --no-pager | head -5
grep -c "ENGINE_CRASH" /tmp/openclaw/watchdog.log 2>/dev/null || echo "0 crashes"

# 2. G-2 FundingArb 監控 daemon 進度（達 demo ≥20 fills 自動寫 audit）
cat /tmp/openclaw/g2_monitor.progress.json

# 3. git 狀態
git status && git log --oneline -5
```

如引擎掛了：`bash helper_scripts/restart_all.sh --engine-only --rebuild`。

---

## 🔴 P0 — 阻塞關鍵路徑（先清才能推 Live Gate）

### P0-0 · RECONCILER-BURST-FIX — 對帳器啟動期誤升級風控 ✅ 2026-04-16
**狀態**：修復完成（待 `restart_all.sh --rebuild` 部署驗證）。方案 A startup grace window 5min 實作。
**根因**（RCA 文件：`docs/references/2026-04-16--reconciler_burst_escalation_rca.md`）：
- 引擎重啟後 warmup baseline 與本地 paper_state 未同步 → 首輪 tick 將 Ghost/Orphan 誤判為 live drift burst
- 2026-04-15 事故：9 drifts（6 ghost + 2 orphan + 1 minor_drift）→ burst streak=1 升 Defensive → FAST_TRACK ReduceToHalf 全組合半倉 + `ft_pause_new_entries` 鎖新開倉 → 46min 才 Cautious→Normal 一路降級
**修復**（方案 A startup grace window 5min）：
- `escalation.rs`：新增 `STARTUP_GRACE_MS = 5 * 60 * 1000` + `ReconcilerState.startup_ms` 欄位
- `evaluate_actions()` 入口：寬限期內早退返空 actions，**不累加** drift_streak / burst_drift_streak / clean_cycles（避免計數累積在寬限結束瞬間集中觸發）
- `check_rest_failure_escalation()` 入口同樣 grace 檢查
- `run_position_reconciler()` 啟動時 `rc_state.startup_ms = now_ms_util()`
- 寬限期內 orphan_handler / V014 audit / baseline update 全部照常運作
**回歸**：
- 6 新 unit tests（escalation.rs）：burst suppression / persistent suppression / single suppression / post-grace normal escalation / REST failure suppression / boundary exclusive / zero startup_ms legacy behaviour
- engine lib 1330 default + 18 reconciler_e2e + 35 stress_integration 全綠 / 0 fail
**解鎖**：P0-1（G-2 FundingArb 驗證）+ P0-3（Phase 5 edge 2w 重評）關鍵路徑
**部署驗收**（operator）：
1. `bash helper_scripts/restart_all.sh --rebuild` 部署新 bin
2. 前 5min：`tail -f /tmp/openclaw/engine.log | grep "startup grace"` 應看到 suppression 日誌（有 drift 時）
3. 前 5min 內 governance 級別保持 `NORMAL`
4. 乾淨環境：30min 內 governance 保持 NORMAL
5. G-2 daemon 重新計時累積 ≥20 fills

### P0-1 · G-2 FundingArb 驗證 🟡 等重啟（P0-4 R1 已合入 2026-04-16，歸檔）
**狀態**：daemon PID 598572 已終止；P0-4 R1 tag 透傳修復已合入（歸檔索引見文件末尾 2026-04-16 條目），engine 重建後 `strategy_name` 將正確分流。下一步是重寫 daemon SQL 口徑並重啟累積 ≥20 真策略退場 fill。
**診斷文件**：`docs/audits/2026-04-16--demo_zero_strategy_exit_audit.md` V2
**阻塞者**：~~P0-4 STRATEGY-CLOSE-TAG-FIX~~ ✅ · ~~FA-PHANTOM-2~~ ✅ · ~~P0-0 RECONCILER-BURST-FIX~~ ✅（待部署）
**驗收**：
- `restart_all.sh --rebuild` 部署 R1 bin；SQL 驗證 `SELECT substring(strategy_name from 1 for 30), COUNT(*) FROM trading.fills WHERE engine_mode='demo' AND ts > '<rebuild_ts>' GROUP BY 1` 出現 `strategy_close:*` 與分離 `risk_close:*` 桶
- 重寫 G-2 daemon SQL 口徑並重啟 → 累積 ≥20 真實策略退場 fill 寫 audit

### P0-2 · LG-1 Paper Trading 21d 觀察期 🕰️
**狀態**：FA-PHANTOM-2 + FIX-PHASE1 部署後等乾淨窗口開始
**目的**：Live 前置條件；≥21d 穩定 paper 運行零事故
**阻塞者**：P0-1（需先確認 funding_arb 邊際可用）
**解鎖**：LG-2/3 shadow→blocking + provider pricing 正式化
**預估**：3 週連續觀察

### P0-3 · Phase 5 策略 Edge 2w 重評 📊
**狀態**：待乾淨 demo 累積 2 週（歸因已通：P0-4 R1 ✅ 2026-04-16）
**判斷**：
- 若 gross edge 翻正 → Phase 5 cost_gate 工作重啟（現有 JS / cost_gate / DL 機械已接線）
- 若 gross edge 仍負 → 策略本身需重做，轉向 EDGE-P3-1 接管（替換 shrunk_bps 為 per-trade 動態預測）或更激進的 EDGE-P2
**阻塞者**：~~P0-0 RECONCILER-BURST-FIX~~ ✅（2026-04-16 修復完成，待部署驗證）。~~P0-1~~ 不必要 — G-2 只覆蓋 funding_arb 子集,Phase 5 整體 edge 用其他 6 策略 fills 已足夠。
**預估**：P0-0 部署後 2 週

### P0-5 · PHANTOM-2-FUP — ReduceToHalf one-shot guard 跨 tick 失效 🆕 2026-04-16
**狀態**：RCA 完成（`docs/references/2026-04-16--phantom2_fup_reduce_to_half_cascade_rca.md`），未排期實作
**症狀**：FA-PHANTOM-2 fix（commit `348a9c5`,`worst_drop_for_held` + sigma 閘）已部署生效（`grep CloseAll engine.log` = **0**），但 `ReduceToHalf` 路徑仍在同 1-2 秒內針對同一 symbol 連續觸發 ≥9 次。實證：
- 引擎日誌 `18:03:41.602042 → .603320`（1.3s 內）9 次 `FAST_TRACK ReduceToHalf`，全是 ORDIUSDT 觸發（held_drop=6.0%/sigma=3.0,positions=2,risk_level=Cautious）
- DB 1-min bucket 統計：16:29 一分鐘 130 fills / 18:03 一分鐘 147 fills（爆發模式）
- R1 baseline 起 2.6h 內 `risk_close:fast_track_reduce_half` = 335 筆 vs `strategy_close:*` = 42 筆(8:1)
**根因推斷**：`tick_pipeline/on_tick.rs:175-228` 的 `ft_reduced_symbols: HashSet<String>` 是 EDGE-P0-1 設計的 one-shot guard,但實際每 tick 進 ReduceToHalf 分支時對 positions 重新展開 → for-loop 對「未在 HashSet」的 sym emit fill。第 1 輪標記後第 2 輪本應整體跳過,但 9 次連發說明 guard 在 risk_level 過渡(Cautious↔Defensive↔Normal)或 ft 重新評估時被清掉了
**修復方案候選**：
- **A**：把 ft_reduced_symbols 升級為 `HashMap<String, ts_ms>`,加 cooldown(建議 ≥60s 同 governance defensive 窗口)
- **B**:每 tick 進 ReduceToHalf 分支時整體 dedup — 若 `positions` 全在 ft_reduced_symbols 中則 early-return,別再 emit_close_fill 0-qty 雜訊
- **C**:把 EDGE-P0-1 重新審計 — 確認 ft_reduced_symbols 在哪些代碼路徑會被 clear(governance.recover()? new tick?),補單元測試
**Why not 立刻動手**：當前未壞 — 只是 reduce 同倉的逐次半倉,功能仍正確。Phase 5 PAUSED 狀態下噪音不造成新傷害。但會放大 DB IO 與引擎日誌 280MB 增長率(同 ENGINE-HEAL `engine_results.jsonl` 111GB 案例)。
**阻塞者**:無(獨立,可在 P0-0 後或併行修)
**解鎖**:G-2 daemon 累積速率 ↑(funding_arb 開倉後不再被 over-fast-track 殲滅)
**驗收**:同條件下 1s 內同 symbol 只觸發 1 次 ReduceToHalf;risk_level 過渡不清空 ft_reduced_symbols(除 governance defensive episode 結束)
**接手指南**:
- 相關程式:`rust/openclaw_engine/src/tick_pipeline/on_tick.rs:175-228`(ft_reduced_symbols 邏輯)、`rust/openclaw_core/src/sm/risk_gov.rs`(risk_level 過渡)
- 觀察手段:`grep "FAST_TRACK ReduceToHalf" /tmp/openclaw/engine.log | head -100` 看時間戳間隔
- 相關 commit:`348a9c5`(PHANTOM-2)、tick_pipeline/tests.rs L171 已有單測 fixture 可擴展
**預估**:0.5d spec + 0.5d 實作 + 0.5d 回歸

**關鍵路徑**:`~~P0-0 reconciler burst fix~~ ✅ → restart_all --rebuild 部署 → P0-3 Phase 5 edge 2w 評估 + P0-2 LG-1 21d → LG-4/5 → Live`(P0-1 G-2 並行驗證 funding_arb 子集,不在主路徑;P0-5 PHANTOM-2-FUP 不阻塞主路徑,可任意時點插入)
**最早 Live 日期**:樂觀估 **W24 末(～2026-05-23)**

---

## 🟡 P1 — W22 當週活躍

> P1-1 EDGE-P3-1 Phase B #3 ONNX loader ✅ 2026-04-16 · P1-2 Step 7b Python route + flag flip ✅ 2026-04-16 — 已歸檔（索引見文件末尾）。

### P1-3 · EDGE-P3-1 Step 7c Python consumer
**狀態**：Rust writer 完（commit `b469448`），`learning.decision_shadow_fills` 寫入正常，但 Python 端沒 consumer routes 用
**工作內容**：shadow fills GUI 視圖 / 審計 / promotion gate 查詢路由（後 Phase B #3 接線後才真正有數據）
**優先級**：P1 下半（#3 先於 7c，因 7c 是讀取端）

### P1-4 · 在真 ETL 資料跑首個 ONNX export
**狀態**：`learning.decision_features` 於 Step 7a 後開始採集；等足夠樣本（≥100k rows per strategy 推薦）
**工作內容**：`run_training_pipeline.py --strategy <name>` → 產 `models/<engine>/<strategy>_vYYYYMMDD.onnx` + symlink
**解鎖**：整個 EDGE-P3-1 Stage 2 shadow mode（P1-1/P1-2 已解鎖 ✅，等此產出首個 artifact 後執行 `ReloadEdgePredictor` IPC 載入）

---

## 🟢 P2 — W23-W24 下週排期

### AI 治理層補強
- [ ] **G-7** ClaudeTeacher 正式啟用（W23）
  - 現況：`consumer_loop.rs` `enabled = false`；learning_store "no consumer"
  - 前置：E3 審查 PASS ✅ + G-3 IPC 認證 ✅ + 21d paper 穩定（P0-2）
- [ ] **G-10** Calibration.py 整合（W23）
  - 現況：`ml_training/calibration.py` 骨架，`apply_calibration` 缺整合入口
  - 目標：isotonic → `run_training_pipeline.py` + ECE < 0.05 門檻
  - 前置：fills 累積 + 2-11 actual training

### Live Gate
- [ ] **LG-2** H0 Gate blocking 驗證（shadow → blocking，W23）
- [ ] **LG-3** provider pricing table 正式綁定（W23）
- [ ] **LG-4** M 章 Supervised Live Gate（W24）
- [ ] **LG-5** N 章 Constrained Autonomous Live（W24）
- [ ] **G-4 / SEC-21** Cookie `secure=True`（HTTPS 部署後，W24）

### QoL
- [ ] **QoL-2** Demo AI cost 無追蹤 — `tab-demo.html` 硬編碼 `'N/A'`，後端無 per-engine AI 調用成本歸因（依賴 G-1 H1-H5 接通）

---

## 🔵 P3 — W25+ 長期專項

### AI Agent 全 5 鏈路（G-1 / R-06）
- [ ] **G-1 / R-06 全 5 agent** — 當前 Conductor 仍 stub；其他 4 agent 已 real（R-06-v2 ✅）
- [ ] **FIX-01** H1-H5 AI Agent 接入（= R-06 完整）
- [ ] **FIX-02** Decision Lease Rust 接入（與 FIX-01 一起）
- [ ] **FIX-12** CSP nonce 遷移（長期）
- [ ] **FUP-8 Phase 2 殘留** — OrderIntent 加 `edge / funding_rate / basis / regime` 欄位（等 G-1 Strategist 串線）
  - Paper sentinel 根治已完，此項僅剩欄位擴充

### ORPHAN-ADOPT-1 Phase 2B
- [ ] **Phase 2B** Strategist 判斷同向信號升級
  - 把 Stage B2 從「正 edge」升級為「Strategist 現時 `would_take(symbol, side)`」
  - `KNOWN_STRATEGY_NAMES` + `EdgeEstimates` probe 降為 fast-path，Strategist 為 slow-path 最終仲裁
  - 前置：G-1 R-02 Strategist agent 在線

### Phase 5 補強（非阻塞，等 P0-3 判斷後定）
- [ ] **5-04~07** DL-1 Symbol Embedding + DL-2 Regime LSTM Shadow
- [ ] **5-08~09** JS + Scorer 整合 + correlation_pairs
- [ ] **5-10~13** E2 + E4 + QC + E5

### EDGE P2（架構層重工）
- [ ] **EDGE-P2-2** OI + Liquidation 信號源 — 給 `bb_breakout` 加領先信號（Bybit WS `tickers` OI + `liquidation` stream）
- [ ] **EDGE-P2-3** Maker order 支持 — fee 5.5 bps → ~1 bps/side（post-only limit；改 IntentProcessor + order_manager + exchange execution layer，根本性改變盈利方程式）

---

## ⚪ P4 — Backlog / Conditional

### WP-F GUI 殘留
- [ ] WP-F/O-xx / AH-08~11（詳 `docs/audits/2026-04-06--consolidated_remediation_report.md` §10.1）

### WP-E4 測試覆蓋
- [ ] T-P2-9 PyO3 bridge tests · T-P2-10 panic-path · T-P2-11 並發
- [ ] T-Q3/Q4/Q7/Q8 覆蓋品質
- [ ] T-I1~I4 tarpaulin / CI 門禁 / 文檔
- [ ] WP-E4/T-P1-1 殘餘 event_consumer 完整事件循環整合測試

### WP-E5 大文件
- [ ] `tick_pipeline.rs` 2117 行 — 留專屬 session

### WP-I 文檔衛生
- [ ] R4-NAME-1 / R4-MEM-1 / R4-REF-ST-1

### 🧹 IP-DEDUP-1 · IntentProcessor 同幣種重發去抖 🆕 2026-04-16
**背景**：Problem 2 診斷（見 `project_engine_mode_tag_live_demo.md` + `project_phase5_promotion_edge_crisis.md`）揭露：cost_gate 拒絕後無 position → 策略每 tick 看到「沒倉位」狀態重發同向 intent（ORDIUSDT 14min 內 8439 筆）。每筆重發都觸發 `evaluate_predictor_gate` → emit DF snapshot → 放大 `learning.decision_features` 寫入量 + 無謂 cost_gate CPU。
**症狀**：Live+LiveDemo 43k DF rows vs Demo 42 rows，98%+ 是殭屍重發（同 symbol+side+strategy 秒級重複）。
**建議方案**：
- IntentProcessor 加 `last_rejected_intent: HashMap<(symbol, is_long, strategy), (ts_ms, reason)>`
- 同 key 在 N 秒（建議 60s，可配置）內重發 → 早退，不計 gate、不 emit DF、寫 `dedup_skipped` 計數器
- 只去抖**被拒絕**的 intent；被批准的 intent 走正常路徑（避免吞掉真正想連續開倉的策略信號）
- 配置項：`risk.intent_dedup.enabled=true` + `dedup_window_secs=60`
**Why**：
- 減 DF 寫入 ≥95%，ML 訓練資料訊噪比提升
- 減 cost_gate CPU / DB IO（Phase 5 負 edge 期間重發主要成本來源）
- 留 counter 讓 GUI 看到「被去抖的 intent 數」保持透明度
- 不修復 Phase 5 edge crisis 本身（那是 G-SR-1 / Strategist agent 的工作），純優化
**Why not 現在做**：Phase 5 策略重做（P0-3 判決後）可能讓負 edge 消失 → 重發率自然下降 → 本優化效益降低。先等 P0-3。
**前置**：P0-3 Phase 5 Edge 2w 重評完成；若 edge 仍負且策略重做時程延長，則提前啟動。
**工作量**：~1d（含 config 欄位、E1/E2/E4、counter GUI 接線）
**驗收**：
- 啟用後同幣種+方向+策略 60s 內重發被早退，`intent_dedup_skipped` counter 遞增
- DF 每日行數 ≥95% 下降（特別是 Live+LiveDemo engine_mode）
- 被去抖不影響**首筆**intent 的 gate 評估 + 仍寫 DF（保留探索樣本）
- 同 symbol 但不同 side（反手）/不同策略 → 不觸發去抖
**接手指南**：
- 相關程式：`rust/openclaw_engine/src/intent_processor/mod.rs`（`evaluate_predictor_gate` 上游）
- 類似機制：`governor_cooldown` 的 24h 冷卻（`mode_state.rs`）、`last_ai_call_time_ms`（cost gate）
- Counter 可復用 `IntentProcessor::stats` 結構

### 前 phase 殘留
- [ ] **2-11** actual training（等 fills 累積）
- [ ] **ort crate** activation（首個 ONNX 模型訓練後 — 現由 P1-4 推進）
- [ ] **4-06** LinUCB live warm-start deployment（script 交付，等首次 v1→v2 遷移）
- [ ] **OC-4** MCP PostgreSQL 自然語言查詢
- [ ] **G-6** Edge estimates 重訓（JS 滾動；P0-2 後）
- [ ] **G-8** cost_gate 可信度評估（依賴 EDGE-P3-1 Stage 2 或 G-6）

### Phase 4-Conditional（觸發後才做）
- [ ] 4-1 PairsTrading（需 3 月協整）· 4-2 Beta Hedging · 4-3 Kalman · 4-5 Mac Studio 遷移 · 4-10 Jump detection

---

## 🗓️ 排期總覽

| 週次 | 日期 | 主要焦點 | 狀態 |
|------|------|---------|------|
| W19-W21 | 04-14~05-02 | 基礎設施 / 安全 / Phase 6 / 3E-ARCH / Audit | ✅ 歸檔 |
| W22 | 05-05~09 | **ENGINE-HEAL FUP-1/2/3 + FIX-PHASE1 · FA-PHANTOM-2 · EDGE-P3-1 Phase A/B + Step 7 · ML-MIT #26 Lane A · GUI fills 鏈** | ✅ 歸檔 |
| W22 末 | 2026-04-15 | P0-1 G-2 驗證（daemon active）· P1-1~4 EDGE-P3-1 Stage 2 推進 | 🟡 進行中 |
| W23 | 05-12~16 | P0-2 LG-1 21d 觀察起點 · G-7 Teacher · G-10 Calibration · LG-2/3 | ⬜ |
| W24 | 05-19~23 | LG-4/5 Live Gate · SEC-21 · QoL-2 | ⬜ |
| W25+ | 05-26+ | EDGE-P3-1 產線化 · Phase 5 補強或重做 · G-1 R-06 全 5 agent | ⬜ |

---

## 🔍 Gap 排期索引（2026-04-10 審計，10 項全錄）

| Gap | 描述 | 排期週 | 狀態 |
|-----|------|--------|------|
| G-1 | AI Agent 5 stub | W22(R-02) ✅ · W25+(R-06 full) | 🟡 |
| G-2 | FundingArb.on_tick() | W22 | 🟡 驗證中（daemon active）|
| G-3 | IPC socket 無認證 | W19 | ✅ |
| G-4 | Cookie secure=False | W24 | ⬜ |
| G-5 | API Rate Limiting | W19 | ✅ |
| G-6 | ML edge 噪音數據 | LG-1 觀察期後 | ⬜ |
| G-7 | ClaudeTeacher disabled | W23 | ⬜ |
| G-8 | cost_gate 可信度低 | EDGE-P3-1 後 | ⬜ |
| G-9 | HMAC dead import | W20 | ✅ |
| G-10 | Calibration.py 骨架 | W23 | ⬜ |

---

## 📚 已完成歸檔索引

- **2026-04-16 STRATEGY-CLOSE-TAG-FIX + EDGE-P3-1 Phase B #3 + DEDUP-PY-RUST**：`docs/archive/2026-04-16--completed_todo_strategy_close_tag_edge_p3_dedup.md` ← **本次整理新增**
- **2026-04-15 W22 ENGINE-HEAL + EDGE-P3-1 + GUI Fills**：`docs/archive/2026-04-15--completed_todo_w22_engine_heal_edge_p3.md`
- **2026-04-14 Phantom-Heal + Engine Self-Healing + EDGE**：`docs/archive/2026-04-14--completed_todo_w22_phantom_heal.md`
- **2026-04-12 全程序鏈審計**：`docs/archive/2026-04-12--completed_todo_full_program_audit.md`
- **W19 + W20 + Phase 6 + 3E-E2 Fix Rounds A-G**：`docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`
- **3E-ARCH 三引擎並行**：`docs/archive/2026-04-11--completed_todo_3e_arch.md`
- **Live GUI P0~P6 + DEAD-PY-1/2 + 1C-4 收尾**：`docs/archive/2026-04-10--completed_todo_live_gui_dead_py.md`
- **Phase 5 P0 promotion + WIRE chain**：commits `5d7d673` → `0e848fa` → `638afa3` → `563d54a` → `5e760be`
- **ARCH-RC1 Session 1A → 1C-4 WRAP**：`docs/archive/2026-04-08--arch_rc1_1c_history_archive.md` + `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`
- **Phase 4 (4-00 ~ 4-21 + 4.1)**：`docs/audits/2026-04-07--phase4_final_signoff_audit.md`
- **Session 11 之前**：`docs/archive/2026-04-06--completed_todo_archive_l3_phases.md`
- **Phase 0/1/2/3 + Rust migration**：`docs/archive/2026-04-04--completed_todo_archive_phase0123_rust.md`
- **已知問題清單**：`docs/KNOWN_ISSUES.md`
- **Bybit API 字典手冊**：`docs/references/2026-04-04--bybit_api_reference.md`

---

## ⚙️ 工作流程速查

```
E1/E1a 並行（最多 5 路）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
角色定義詳見 CLAUDE.md §八
```

**Bybit API 開發必查**：先讀 `docs/references/2026-04-04--bybit_api_reference.md`。

**風控參數修改強制原則**：所有風控/止損/cost-gate/regime 參數必須透過 IPC `patch_risk_config` 單一通道更新。

**腳本速查**（詳 `helper_scripts/SCRIPT_INDEX.md` + `README.md` 「常用腳本」章節）：
```
改了代碼需部署              → bash helper_scripts/restart_all.sh --rebuild
只想清交易所持倉             → bash helper_scripts/clean_restart.sh --yes
開發告一段落要清 PnL/勝率    → bash helper_scripts/fresh_start.sh --yes
臨時停機 debug              → bash helper_scripts/stop_all.sh
```
