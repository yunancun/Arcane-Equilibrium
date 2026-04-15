# OpenClaw TODO — 工作計劃清單

**最後更新：2026-04-15**（EDGE-P3-1 spec v1.0 → v1.3 四輪審查完成，GREEN — Stage 0 可開工；worklog: `docs/worklogs/2026-04-15--edge_predictor_spec_v1_to_v1_3.md`；ENGINE-HEAL + FUP-8 Phase 2 已 deploy 並 DB 驗證）
**測試基準線**：Rust **engine lib 1198 + core 372 + e2e 33 + stress 35 = 1638** · Python **2852 passed (5 skipped · 0 fail)** · ml_training **135 passed (6 skipped)**

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> 歷史歸檔索引在文件末尾。詳細完成度視角見 README.md。

---

## 🎯 Immediate Next Actions（依賴 + 阻塞力排序）

| # | 項目 | 預估 | 阻塞者 | 解鎖 |
|---|------|------|-------|------|
| ~~1~~ | ~~🚀 **ENGINE-HEAL-DEPLOY**~~ ✅ 2026-04-15 PID 403560 跑 binary mtime 01:55（含 ENGINE-HEAL Fix 1/3/4 + FA-PHANTOM-1 + FUP-8 Phase 1&2 全數到位）；DB 驗證 paper intents.details 非 NULL 且 `is_sentinel=false` + 真實 sized qty；canary 持續觀察中（≥1h 軟門檻不阻塞後續 action） | — | — | — |
| **2** | 🧪 **G-2 FundingArb 驗證重啟** — deploy 後：manual entry 1 → paper_state 有倉 → IPC close → DB 出現 close fill with realized_pnl；再累積 ≥20 乾淨 fills 分析 edge | 2-3 d | ~~#1~~ ✅ | Phase 5 歸因量化確認 · LG-1 觀察期起點 |
| **3** | 🕰️ **LG-1 Paper Trading 21d（重新定位）** — EDGE-P0/P1 + FA-PHANTOM-1 + FUP-8 部署後啟動正式觀察期；不再綁定 05-01 | 3 w | ~~#1~~ ✅, #2 | Live Gate · LG-2/3 |
| ~~4~~ | ~~FA-PHANTOM-1-FUP-7~~ ✅ 2026-04-15 operator 選 C，註釋已加到 `fast_track.rs:39-57`（見下方 FA-PHANTOM-1 留尾段） | — | — | — |
| **5** | 📊 **Phase 5 策略 Edge 2w 重評** — 乾淨 paper 2w 後重算 per-strategy gross edge。若翻正 → Phase 5 cost_gate 工作重啟；若仍負 → 策略本身需重做（EDGE-P2/P3） | 2 w | Action #2 | Phase 5 restart / rebuild 決策 |

---

## 🗓️ 排期總覽（2026-04-14 更新）

| 週次 | 日期 | 主要焦點 | 狀態 |
|------|------|---------|------|
| W19-W21 | 04-14~05-02 | 基礎設施 / 安全 / Phase 6 / 3E-ARCH / Audit | ✅ 歸檔 |
| W22 | 05-05~09 | **G-SR-1 + R-02/R-06-v2**（提前完成）· **FA-PHANTOM-1 + FUP-1~8 全數結清** · **ENGINE-HEAL deploy** · **G-2 驗證重啟** | 🟡 進行中 |
| W23 | 05-12~16 | **LG-1 觀察期**（if clean）· G-7 Teacher · G-10 Calibration · LG-2/3 | ⬜ |
| W24 | 05-19~23 | **LG-4/5 Live Gate**（M/N 章）· SEC-21 · QoL-2 | ⬜ |
| W25+ | 05-26+ | **EDGE-P3-1 Realized Edge Predictor** · Phase 5 補強或重做 · R-06 全 5 agent | ⬜ |

**關鍵路徑**：`#1 DEPLOY → #2 G-2 → #3 LG-1 21d → LG-4/5 → Live`
**最早 Live 日期**：視 LG-1 乾淨觀察期起點。樂觀估 **W24 末**（～2026-05-23），保守估 W25 末。

---

## 🟡 W22 活躍工作（當前週）

### 部署窗口（Action #1）

- [x] **ENGINE-HEAL-DEPLOY** ✅ 2026-04-15 — PID 403560 跑 binary mtime 01:55，含 ENGINE-HEAL Fix 1/3/4 + FA-PHANTOM-1 leverage-aware margin + FUP-8 Phase 1（sentinel flag `f6b07cd`）+ FUP-8 Phase 2（paper 走 sizing `2061310`）全數到位
  - DB 驗證：paper intents 10 筆最近 3 分鐘樣本，`submitted_qty` 真實 sized（0.47~31742），`is_sentinel=false`
  - Canary 觀察：0 `FAST_TRACK CloseAll fired` / 0 panic / 0 crash 於持續運行中；≥1h 軟門檻待自然累積（不阻塞後續 action）

### G-2 FundingArb 驗證（Action #2，BLOCKED by #1）

- [ ] **G-2** FundingArb 策略驗證 + 參數調優
  - OC-5 ✅：FundingArb on_tick() 完整實現（entry/exit/cooldown/basis/edge），index_price TickContext 全鏈路
  - 2026-04-14 驗證失敗 — 窗口 17:33-21:55 內 22 paper funding_arb fills 全為 PHANTOM（FA-PHANTOM-1 致瞬平）
  - **恢復流程（#1 deploy 後）**：
    1. 驗證修復：手動跑 funding_arb paper 1 個 entry → 查 paper_state positions 有出現 → IPC close → DB 出現 close fill with realized_pnl
    2. 重新啟動驗證窗口（paper `funding_threshold=0.0001 / total_cost_bps=1.0` 臨時降，4h 累積後還原）
    3. 累積 ≥20 乾淨 fills 後分析 edge + 撰寫 audit note

### FA-PHANTOM-1 留尾 — 已清

- [x] **FA-PHANTOM-1-FUP-7** operator 選 C（保留 90% 為 cash-mode fail-safe + 加註釋）— 2026-04-15 完成
  - `fast_track.rs:39-57` 加了 ~19 行註釋說明：(a) 90% 是 Bybit MMR 物理常數不可 auto-scale；(b) margin_utilization_pct 本身 post FA-PHANTOM-1 fix 已是 leverage-aware；(c) 當前高槓桿配置下不觸發是刻意的 cash-mode 兜底；(d) 反 pattern 警告不要為「看起來死碼」去降閾值（會重開 FA-PHANTOM-1 類 false-positive）
  - 純註釋改動，`cargo check` 通過，無新測試需求

### Phase 5 策略 Edge 觀察（Action #5）

- [ ] **PH5-VERIFY-1** 乾淨 paper 2w 重評 — EDGE-P0/P1 + FA-PHANTOM-1 fix 部署後 2 週數據，重新評估 gross edge
  - 若 gross edge 翻正 → Phase 5 cost_gate 工作重啟
  - 若 gross edge 仍負 → 策略本身需重做（EDGE-P2/P3 排期）

---

## 🟢 W23-W24 下週工作

### AI 治理層補強（G-1 後續）

- [ ] **G-7** ClaudeTeacher 正式啟用（W23）
  - 現況：consumer_loop.rs `enabled = false`（啟動時 fail-closed）+ learning_store "currently has no consumer"
  - 前置：E3 審查 PASS ✅ + G-3 IPC 認證 ✅ + 21d paper 穩定（LG-1）

- [ ] **G-10** Calibration.py 整合（W23）
  - 現況：ml_training/calibration.py 骨架，apply_calibration 缺整合入口
  - 目標：calibrate_isotonic → run_training_pipeline.py，加入 ECE < 0.05 門檻
  - 前置：fills 累積 + 2-11 actual training

### Live Gate（W23-W24）

- [ ] **LG-2** H0 Gate blocking 驗證（shadow → blocking，W23）
- [ ] **LG-3** provider pricing table 正式綁定（W23）
- [ ] **LG-4** M 章 Supervised Live Gate（W24）
- [ ] **LG-5** N 章 Constrained Autonomous Live（W24）
- [ ] **G-4 / SEC-21** Cookie `secure=True`（HTTPS 部署後，W24）

**完成後**：換入 mainnet API key，系統即進入真實 Live（零代碼改動）。

### QoL

- [ ] **QoL-2** Demo AI cost 無追蹤 — `tab-demo.html` 硬編碼 `'N/A'`，後端無 per-engine AI 調用成本歸因機制（依賴 G-1 H1-H5 AI 治理層接通後才有意義）

---

## 🔮 W25+ 長期工作

### 🧠 EDGE-P3-1 Realized Edge Predictor（取代 JS shrinkage，解鎖 Phase 5 cost_gate）

- [ ] **EDGE-P3-1** 🧠 **Realized Edge Predictor** — shrunk_bps 退役 · 單筆單子 ex-ante edge 預測
  - **一句話**：`shrunk_bps` 是「策略**歷史平均**賺多少」（靜態）；此項改為「**這一筆**在現在市場條件下預期賺多少」（quantile LightGBM 動態預測）
  - **Why**：當前所有策略 gross edge ≈ 0，shrunk_bps 塌到 -35.72 bps → cost_gate 形同虛設。LightGBM 管線是空殼。LinUCB 只做 arm 選擇。三件事同一個洞：**沒有模型把「決策瞬間 features」映射到「實現 edge」**
  - **模型**：`P(realized_edge_bps | context)` per-strategy quantile LGBM (q10/q50/q90) + CQR + monotone rearrangement
  - **Features**（17 維，決策瞬間快照，禁 look-ahead）：Regime 5 · Microstructure 3 · Strategy 3 · Position 3 · Time 3
  - **Label**：`realized_net_edge_bps = (exit-entry)/entry × side − closed_fees_bps`，close fill 時回填；grid VWAP merge / 其他 qty-weighted blend
  - **接線**：替換 cost_gate 比較邏輯 → `predicted_median_edge − k×(median−q10) > cost` 才放行；`q10 > 0` 才加倉
  - **規格演化**（2026-04-15 完成 4 輪審查）：v1.0 → v1.1（round-1 QC/QA）→ v1.2（round-2 F1-F10，816→1019 行）→ v1.3（round-3 U1-U4 + M1，1019→1101 行）→ round-4 **GREEN**
  - **規格路徑**：`docs/references/2026-04-15--edge_predictor_spec.md`（1101 行 · CC 13 項 · T1-T23 命名測試）
  - **Worklog**：`docs/worklogs/2026-04-15--edge_predictor_spec_v1_to_v1_3.md`（規格四輪演化完整記錄）
  - **分工（Stage 0 可開工，#25 + #27 可並行）**：
    - **FA** ✅ spec v1.3 GREEN（commit `9141e08`）
    - **PA** (#25) → SQL migration（`learning.decision_features` + `learning.decision_shadow_fills` + index）+ `parquet_etl.py` 補實現 + train 觸發器
    - **ML-MIT** (#26) → quantile LGBM + CQR + CPCV + isotonic calibration + 離線 pinball loss / decile lift（blocked by #25）
    - **AI-E** (#27) → Rust `edge_predictor/` module + PyO3 ONNX runtime + `cost_gate` 接入 + shadow flag + IPC 熱重載 + `write_toml_atomic_fsynced` helper 升級（`store.rs:231-244` 現無 fsync）+ `PipelineCommand::EmitShadowFill` IPC
    - **CC** (#28) → 13 項必查（v1.3 CC clist）+ T1-T23 regression（blocked by #27）
  - **安全門檻**（不可違背）：Shadow ≥14d（#29）· pinball loss 對比常數模型 >10% 才 promote · Feature freeze time = entry 瞬間 · Per-strategy 獨立模型 · 推理失敗 fail-closed → 回退現有 shrinkage · 不觸 LinUCB · 兩階段提交防 half-enabled · macOS CI `aarch64-apple-darwin`（M1/M2/M3/M4 → M5 Ultra/Max 部署目標，見 memory `project_mac_deployment_target.md`）
  - **Stage 0 收尾前 housekeeping**（Round-4 YELLOW-nit，非阻塞）：§7.1 加 ort macOS dylib bundling 提醒 · CC #13 加 strace Linux-only 註記
  - **狀態**：🟢 spec GREEN · Stage 0 可開工（#25 PA + #27 AI-E 並行啟動）

### Phase 6 擴展

- [ ] **ORPHAN-ADOPT-1 Phase 2** — 真正 Adopt 路徑
  - 前置：Strategist/Guardian AI agent 在線 ✅ + StopManager adopt 接口 + 合成 StrategyId 規約
  - 實作：Stage B2/B3 策略信號匹配 → 合成 `StrategyId` → 原子三件事（注入 `position_map` + 綁 hard/trailing stop + 寫 `ORPHAN_ADOPTED` audit）→ 任一失敗降級 Close
  - Phase 1 已預留 `OrphanDecision::Adopt` enum variant + `OrphanStage::SoftAdoptEligible` 分支，Phase 2 改 dispatch 即可

### AI Agent 全 5 鏈路

- [ ] **G-1 / R-06 全 5 agent**（W25+）— 當前 Conductor 仍 stub，其他 4 agent 已 real（R-06-v2 ✅）
- [ ] **FIX-01** H1-H5 AI Agent 接入（= R-06 完整）
- [ ] **FIX-02** Decision Lease Rust 接入（與 FIX-01 一起）
- [ ] **FIX-12** CSP nonce 遷移（長期）
- [ ] **FUP-8 Phase 2** OrderIntent 加 edge/funding_rate/basis/regime 欄位（與 G-1 Strategist 串線同步）
  - **Paper sentinel 根治 ✅**（2026-04-15）：`IntentResult` 加 `approved_qty: f64` 字段，`process()` 在成功路徑暴露 Kelly+P1 sizing 後的 `final_qty`；`on_tick.rs:721` 改傳 `result.approved_qty` 給 `persist_intent`，paper 的 `submitted_qty` 現在記錄真實 sized qty（非 1e9 sentinel）。既有 sentinel guard 降為安全網（IPC 路徑 + 未來新 caller 防呆）。+2 測試 `test_fup8_phase2_approved_qty_{exposed_on_success,zero_on_rejection}`。
  - **Sentinel 的使用場景**：5 策略 `default_qty/DEFAULT_QTY_PER_GRID = 1e9`（`grid_trading.rs:172`, `funding_arb.rs:62`, `bb_*`.rs, `ma_crossover.rs`）作為「請幫我 size」信號 — 此設計本身不需改動
  - **剩餘工作**：OrderIntent 加 `edge/funding_rate/basis/regime` 欄位（等 G-1 Strategist）

### Phase 5 補強（非阻塞）

- [ ] **5-04~07** DL-1 Symbol Embedding + DL-2 Regime LSTM Shadow
- [ ] **5-08~09** JS+Scorer 整合 + correlation_pairs
- [ ] **5-10~13** E2 + E4 + QC + E5

### EDGE P2（架構層，大工程）

- [ ] **EDGE-P2-2** OI + Liquidation 信號源 — 給 bb_breakout 加領先信號（Bybit WS `tickers` OI + `liquidation` stream）
- [ ] **EDGE-P2-3** Maker order 支持 — fee 從 5.5 bps/side → ~1 bps/side（post-only limit order，改 IntentProcessor + order_manager + exchange execution layer，根本性改變盈利方程式）

---

## 🧰 WP Backlog（低優先 · 維護性）

詳見 `docs/audits/2026-04-06--consolidated_remediation_report.md` §10。

### WP-F GUI 殘留

- [ ] WP-F/O-xx / AH-08~11（詳見 §10.1）

### WP-E4 測試覆蓋

- [ ] T-P2-9 PyO3 bridge tests / T-P2-10 panic-path / T-P2-11 並發
- [ ] T-Q3/Q4/Q7/Q8 覆蓋品質
- [ ] T-I1~I4 tarpaulin / CI 門禁 / 文檔
- [ ] WP-E4/T-P1-1 殘餘 event_consumer 完整事件循環整合測試

### WP-E5 大文件

- [ ] tick_pipeline.rs 2117 行 — 留專屬 session

### WP-I 文檔衛生

- [ ] R4-NAME-1 / R4-MEM-1 / R4-REF-ST-1

---

## 📦 殘留延後（前 phase，非阻塞）

- [ ] **2-11** actual training（需足夠 trading.fills 累積）
- [ ] **ort crate** activation（首個 ONNX 模型訓練後）
- [ ] **4-06** LinUCB live warm-start deployment（script 已交付，等首次 v1→v2 遷移）
- [ ] **OC-4** MCP PostgreSQL 自然語言查詢
- [ ] **G-6** Edge estimates 重訓（JS 滾動，LG-1 觀察期後重訓）
- [ ] **G-8** cost_gate 可信度評估（依賴 EDGE-P3-1 或 G-6）

### Phase 4-Conditional（觸發後）

- [ ] 4-1 PairsTrading（需 3 月協整）/ 4-2 Beta Hedging / 4-3 Kalman / 4-5 Mac Studio 遷移 / 4-10 Jump detection

---

## 🔍 Gap 排期索引（2026-04-10 審計，10 項全錄）

| Gap | 描述 | 排期週 | 狀態 |
|-----|------|--------|------|
| G-1 | AI Agent 5 stub | W22(R-02) ✅ + W25+(R-06 full) | 🟡 |
| G-2 | FundingArb.on_tick() | W22 | 🟡 進行中（BLOCKED by deploy）|
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

- **2026-04-14 Phantom-Heal + Engine Self-Healing + EDGE**：`docs/archive/2026-04-14--completed_todo_w22_phantom_heal.md`（ENGINE-HEAL 4 Fix + FA-PHANTOM-1 修復 + FUP-1/2/3/4/5/6/8 + EDGE-P0/P1/P2-1 + QoL-1/3 + ORPHAN-ADOPT-1 Phase 1 + WP-F UX-07~10 + ZOMBIE-API-SVC + PNL-5/6 + OC-5）
- **2026-04-12 全程序鏈審計**：`docs/archive/2026-04-12--completed_todo_full_program_audit.md`（P0 8/8 + P1 19/19 + P2 Rust 7/7 + PNL-1~4 + QoL-4）
- **W19 + W20 + Phase 6 + 3E-E2 Fix Rounds A-G + 晚間 Audit BLOCKERs**：`docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`
- **3E-ARCH 三引擎並行**：`docs/archive/2026-04-11--completed_todo_3e_arch.md`（S0-S13 + 10 BLOCKER + 7 MAJOR）
- **Live GUI P0~P6 + DEAD-PY-1/2 + 1C-4 收尾**：`docs/archive/2026-04-10--completed_todo_live_gui_dead_py.md`
- **Phase 5 P0 promotion + WIRE chain**：commits `5d7d673` → `0e848fa` → `638afa3` → `563d54a` → `5e760be`
- **ARCH-RC1 Session 1A → 1C-4 WRAP**：`docs/archive/2026-04-08--arch_rc1_1c_history_archive.md` + `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`
- **Phase 4 (4-00 ~ 4-21 + 4.1)**：`docs/audits/2026-04-07--phase4_final_signoff_audit.md`
- **Session 11 之前**：`docs/archive/2026-04-06--completed_todo_archive_l3_phases.md`
- **Phase 0/1/2/3 + Rust migration**：`docs/archive/2026-04-04--completed_todo_archive_phase0123_rust.md`
- **已知問題清單**：`docs/KNOWN_ISSUES.md`
- **Bybit API 字典手冊**：`docs/references/2026-04-04--bybit_api_reference.md`
- **工程日誌（2026-04-14 ENGINE-HEAL）**：`docs/worklogs/2026-04-14--engine_self_healing.md`
- **工程日誌（2026-04-15 EDGE-P3-1 規格四輪演化）**：`docs/worklogs/2026-04-15--edge_predictor_spec_v1_to_v1_3.md`

---

## ⚙️ 工作流程速查

```
E1/E1a 並行（最多 5 路）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
角色定義詳見 CLAUDE.md §八
```

**Bybit API 開發必查**：先讀 `docs/references/2026-04-04--bybit_api_reference.md`。

**風控參數修改強制原則**：所有風控/止損/cost-gate/regime 參數必須透過 IPC `patch_risk_config` 單一通道更新。
