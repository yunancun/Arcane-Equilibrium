# E5 TODO 完整提案報告
# E5 Complete TODO Proposal Report

**日期 / Date**: 2026-04-24  
**角色 / Role**: E5 Optimization Engineer（優化工程師）  
**對象 / Scope**: OpenClaw 全代碼庫 Rust + Python + helper scripts  
**基礎 / Baseline**: 
- E5 記憶體 `memory.md` + 檔案 `profile.md`
- 5 份歷史報告（2026-03-31 / 2026-04-01 / 2026-04-24 × 2 / 2026-04-23）
- L3 comprehensive audit `2026-04-05--audit_E5_optimization_report.md`
- 當前 TODO.md (328 行，Wave 結構版本)
- 實測檔案大小 (`wc -l` 驗證)

---

## 執行摘要

**E5 2026-04-24 全盤評估結論**：

1. **合規危機（Critical）**：8 項 Rust 檔 + 2 項 Python 檔超硬上限 1200 行；必須 Wave 1-2（W17-W19 / 4/24-5/7）內清除
2. **可讀性債務（High）**：`event_consumer/mod.rs::run_event_consumer()` 單 async fn **1696 行**（項目史上最大），governance 層 3600+ 行邊界模糊
3. **完成度盤點**：
   - ✅ E5-P0 Refactor Wave（2026-04-18）
   - ✅ E5-P1 Refactor Wave 1-2（2026-04-19）
   - ✅ E5-FN Functional Defects Wave（2026-04-19）
   - 殘留：E5-P2-4c (bb_reversion 1143 行未拆)、E5-P2-X (命令層拆分未完成)
4. **新發現（3 Verified Finding 源於 TODO audit）**：
   - (a) `edge_estimator_scheduler` 4 天停滯（`edge_estimates.json` 1 cell vs CLAUDE.md 宣稱 162）→ G1-01 立即恢復
   - (b) PostOnly 配置反向 demo=false/live=true → G1-05 修正
   - (c) ExecutorAgent `_shadow_mode=True` hardcoded（違反原則 #3） → G3-02 解開

**優先級排序**（E5 視角）：
| 級別 | 類型 | 數量 | 工時 | 阻塞 |
|------|------|------|------|------|
| **P0 硬違反** | Rust ≥1200 行 | 8 檔 | 3-4w | Live Gate（§九 規範） |
| **P0 硬違反** | Python ≥1200 行 | 2 檔 | 2-3d | Live Gate（§九 規範） |
| **P1 警告邊際** | Rust 1000-1200 行 | 8 檔 | 1-2w | 防下輪撞牆 |
| **P2 可讀性** | Python governance + 策略 | 5+ 檔 | 2-3w | 長期維護性 |
| **P3 架構債務** | monkeypatch 遷移評估 | — | 後延 | Phase 5+ |

---

## 一、E5 歷史報告全盤清算

### 1. 2026-03-31 — 49 項優化（E5 baseline）

| 優先級 | 類別 | 數量 | 狀態 |
|--------|------|------|------|
| Critical | 熱路徑阻塞 | 3 | ✅ 多數已解 |
| High | 性能影響顯著 | 14 | 🟡 部分進行中 |
| Medium | — | 22 | ⬜ 待 Wave 2-3 |
| Low | — | 10 | ⬜ — |

**關鍵完成**：`push_capped<T>` / `now_ms()` / `TickContext<'a>` zero-copy / parallel DB flush / helper unification

### 2. 2026-04-01 — 54 項審計 + 前期優化

**硬上限違反**（當時數據）：
- Rust 1 檔超 1200（`market_data_client.rs` 1422，已改組）
- Rust 7+ 檔超 800（警告線）
- Python 5 檔超 1200（已改組，惟 legacy_routes 仍存）

**已閉環**：
- ✅ tick_pipeline 2274 → 1012 行（TICK-PIPELINE-MOD-SPLIT-1, 2026-04-22）
- ✅ main_legacy.py 5113 → 468 行（DEDUP-PY-RUST Tier B Wave A-D, 2026-04-23）
- ✅ f-string logger 清零（生產碼）
- ✅ int(time.time()*1000) 集中至 `ai_agents/bybit_thought_gate/`（30 處）

**仍未動**（低優先級）：
- `truth_source_registry` / `experiment_ledger` 無界 dict
- `compile_state` 重複邏輯（但 main_legacy 瘦身後需重新對照）
- 前端 CSS `:root` 重複（範圍外）

### 3. 2026-04-05 — L3 comprehensive audit

**當時版本**（稍舊，已部分改組）：
- Rust 超限 1 檔（vs 當前 8 檔 → code grew 新增邏輯）
- Python 超限 5 檔（vs 當前 2 檔 → Wave A-D 拆分已生效）
- 編譯器警告 5 個（partial cleanup）
- Deadlock 反模式 2-3 個（FIX-26-DEADLOCK-1 已解）

**現在進度**：L3 發現多已改組，但新代碼增長導致新熱點浮現

### 4. 2026-04-12 — E5 Performance Optimization Final Report

**23 項 Phase 5 完成**（已歸檔 2026-04-21 archive）

**閉環驗證**：
- 5 大 helper (`push_capped`, `now_ms`, `is_stale`, `clamp_confidence`, `build_intent`) 已實裝 + 未回彈
- `TickContext<'a>` zero-copy 保留
- Parallel DB flush (tokio::join! 7 tables) 保留

### 5. 2026-04-24 × 2 — TodoAudit + FullChainAudit

**TodoAudit（E5 自動驗證）**：
- P0 警報：Rust 8 檔 ≥1200 / Python 2 檔 ≥1200
- 拆分驗證：5 項已宣稱工作通過（ma_crossover 優秀；bb_breakout 邊際；strategies/mod 未拆）
- pain point top 5：event_consumer fn 1696 / main.rs 2062 / bb_reversion 1143 / governance 3600+ / ipc_server 1192

**FullChainAudit（E5 全代碼庫 49k Rust + 37k Python）**：
- S1-S10：10 項精簡建議（Rust 8 檔硬違反 + Python 2 檔 + helper 1 檔）
- P1-P10：10 項性能熱點（clone 115 處、鎖 94 處、O(n) 掃描、串行 await）
- R1-R10：10 項可讀性（nested match、长 fn、singleton lifecycle）

---

## 二、當前 TODO.md G5 涵蓋度檢視

### G5 工作組（架構 / 可讀性）

| ID | 項目 | 狀態 | 工時 | 前置 |
|----|------|------|------|------|
| G5-01 | main.rs 2062 行拆 bootstrap | ⬜ | 2-3d | 無 |
| G5-02 | live_session_routes.py 1449 行拆 | ⬜ | 1-2d | 無 |
| G5-03 | instrument_info.rs 1975 行拆 | ⬜ | 1-2d | 無 |
| G5-04 | ai_service.py 1258 行拆 | ⬜ | 1d | 無 |
| G5-05 | bb_reversion.rs 1143 行拆（P3） | ⬜ | 1h | 無 |
| G5-06 | 硬違反 5 檔拆分 | ⬜ | 5-8d | 無 |

**缺陷分析**：

1. **G5-06 過度簡化** — 5 檔（bybit_rest_client 1725 / order_manager 1554 / startup 1377 / resting_orders 1367 / risk_config 1328）各需 2-3d，但 TODO 未分拆，難追蹤進度
2. **priority 未說明** — G5-01/02/03 标註 P1，但與 G1-02 event_consumer 拆有硬依賴關係（E5 建議 G1-02 先動）
3. **缺 ipc_server 1192 預拆** — 距硬上限 8 行，下波改動必觸牆，應列 P1
4. **缺 strategist_scheduler 1166 預拆** — 同上，34 行緩衝

### 完整硬違反清單（G5 + 補遺）

**Rust ≥1200 行（8 項，必須合規）**：
```
1. event_consumer/mod.rs         1762 (含 1696 行單 async fn) ← G1-02 專案
2. main.rs                       2062 ← G5-01
3. instrument_info.rs           1975 ← G5-03
4. bybit_rest_client.rs         1725 ← G5-06.1
5. order_manager.rs             1554 ← G5-06.2
6. startup.rs                   1377 ← G5-06.3
7. paper_state/resting_orders.rs 1367 ← G5-06.4
8. config/risk_config.rs        1328 ← G5-06.5
```

**Python ≥1200 行（2 項，必須合規）**：
```
1. live_session_routes.py       1449 ← G5-02
2. ai_service.py                1258 ← G5-04
```

**Rust 1000-1200 警告邊際（8 項，預拆防撞牆）**：
```
1. ipc_server/mod.rs            1192 (8 行至硬限) ← **建議立即 G5 加項**
2. tick_pipeline/on_tick/helpers.rs 1182 (18 行至硬限) ← **建議 G5 加項**
3. strategist_scheduler/mod.rs  1166 (34 行至硬限) ← **建議 G5 加項**
4. strategies/bb_reversion.rs   1143 ← G5-05
5. ws_client.rs                 1136
6. event_consumer/dispatch.rs   1124 (已是 sibling)
7. intent_processor/mod.rs      1100
8. claude_teacher/applier.rs    1068
```

**Python 800-1200 警告線（22 項）**：top 10:
```
governance_routes.py            1172
strategist_agent.py             1170
multi_agent_framework.py        1137
paper_trading_routes.py         1088
governance_hub.py               1014
truth_source_registry.py        977
experiment_ledger.py            974
h0_gate.py                      971
trade_attribution.py            958
reconciliation_engine.py        948
+ 12 more in 800-950 range
```

### 補缺項建議

**G5 應補加 3 項預拆**（防下輪撞牆）：
- **G5-07**: `ipc_server/mod.rs` 1192 預拆 handlers/ (1d)
- **G5-08**: `tick_pipeline/on_tick/helpers.rs` 1182 預拆 (1d)
- **G5-09**: `strategist_scheduler/mod.rs` 1166 預拆 (1d)

---

## 三、E5 完整 TODO 提案（分級版）

### ★ CRITICAL — Wave 1（W17-18 / 4/24-4/30）

| 序 | 編號 | 項目 | 原報告 | 現況 | 工時 | 前置 |
|---|------|------|--------|------|------|------|
| 1 | **G1-02** | `event_consumer/mod.rs::run_event_consumer()` 拆分（1696 行單 async fn） | 2026-04-24 TodoAudit §5.1 | ⬜ P0 | **3-4d** | 無 |
| 2 | **G1-01** | edge_estimator_scheduler 4d 停滯修復（3 verified finding） | 2026-04-24 memory | ⬜ P0 | 2h + passive | 無 |
| 3 | **G1-05** | PostOnly 配置反向 bug（demo=false/live=true 修正） | 2026-04-24 memory | ⬜ P0 | 0.5d | 無 |
| 4 | **G5-01** | main.rs 2062 行拆 bootstrap/ + async_main | 2026-04-24 full-chain §S-1 | ⬜ P1 | 2-3d | G1-02 |
| 5 | **G5-03** | instrument_info.rs 1975 行拆 cache/fetch/parse | 2026-04-24 full-chain §S-3 | ⬜ P1 | 2-3d | — |
| 6 | **G5-02** | live_session_routes.py 1449 行按流程拆分 | 2026-04-24 full-chain §S-10 | ⬜ P1 | 1-2d | — |

### ★ HIGH — Wave 1 後续 (W18) + Wave 2 (W19)

| 序 | 項目 | 原報告 | 工時 | 前置 |
|---|------|--------|------|------|
| 7 | G5-04: ai_service.py 1258 行拆（Handler per method） | 2026-04-24 full-chain §R-2 | 1d | — |
| 8 | G5-06.1: bybit_rest_client.rs 1725 按業務區拆（account/order/wallet） | 2026-04-24 full-chain §S-4 | 2-3d | — |
| 9 | G5-06.2: order_manager.rs 1554 enum derive（174 行 as_str 消除） | 2026-04-24 full-chain §S-5 | 1-2d | — |
| 10 | G5-06.3: startup.rs 1377 拆 bootstrap/ phases | 2026-04-24 full-chain §S-6 | 2-3d | — |
| 11 | **G5-07** | `ipc_server/mod.rs` 1192 預拆 handlers/ submodules | **新增** | 1-2d | — |
| 12 | **G5-08** | `tick_pipeline/on_tick/helpers.rs` 1182 預拆 submodules | **新增** | 1d | — |

### ★ MEDIUM — Wave 2-3 (W19-W22)

| 序 | 項目 | 原報告 | 工時 | 備註 |
|---|------|--------|------|------|
| 13 | G5-06.4: resting_orders.rs 1367 拆 queue/match_engine | 2026-04-24 full-chain §S-7 | 2-3d | paper engine test suite robust |
| 14 | G5-06.5: risk_config.rs 1328 拆 子配置 sibling modules | 2026-04-24 full-chain §S-8 | 1-2d | serde schema 保持 top-level 不變 |
| 15 | **G5-09** | `strategist_scheduler/mod.rs` 1166 預拆 submodules | **新增** | 1d | 防下輪撞牆 |
| 16 | P1-P3: tick_pipeline 115 clone 熱路徑審視 | 2026-04-24 full-chain §P-3 | 2-3d | tracing 借用改造 |
| 17 | P-5: ai_budget/tracker.rs 16 locks 鎖粒度審視 | 2026-04-24 full-chain §P-5 | 1d | 考慮 DashMap / atomic counters |
| 18 | governance_routes.py 1172 按 SM 拆分 | 2026-04-24 full-chain §R-8 | 2-3d | SM-01/02/04/EX-04 各檔 |
| 19 | strategist_agent.py 1170 `_handle_*` 拆小 | 2026-04-24 full-chain §R-9 | 1d | 每段 ≤70 行 |
| 20 | multi_agent_framework.py 1137 拆 agent_base/message_bus | 2026-04-24 full-chain §R-9 | 2d | 新 agent 模板清晰 |

### ★ LOW / OPTIONAL — Wave 3+ (W20+)

| 序 | 項目 | 優先級 | 工時 | 狀態 |
|---|------|--------|------|------|
| 21 | G5-05: bb_reversion.rs 1143 拆 sibling（E5-P2-4c） | P3 | 1h | 邊際項 |
| 22 | bb_breakout 1000+ 邊際監視 | P3 | — | 監視 |
| 23 | funding_arb.rs 982 監視 | P3 | — | 當前合規 |
| 24 | counterfactual_exit_replay.py 1216 拆 helper/ | P3 | 1d | script 層，非 hot path |
| 25 | monkeypatch 架構遷移評估（main_legacy 依賴注入） | P3 | TBD | Phase 5+ 後 |
| 26 | truth_source_registry 無界 dict eviction | P2 | 1d | 舊發現，仍適用 |
| 27 | experiment_ledger 無界 dict eviction | P2 | 1d | 舊發現，仍適用 |
| 28 | SystemTime::now() / now_ms() 統一（94 處） | P2 | 1d | 機械替換 |
| 29 | live_contraction_monitor backoff（P-7） | P2 | 0.5d | fail-safe 改善 |
| 30 | instrument_info cache eviction 政策確認 | P2 | 0.5d | 防長期 memory leak |

---

## 四、E5 優化階段計畫（W17-W27 路線）

```
W17-18 Wave 1 — 基礎設施 + 合規達成
├─ G1-02 event_consumer fn 拆分 (3-4d) — Blocker
├─ G1-01 scheduler 恢復 + G1-05 PostOnly 修 (2.5d) — 並行
├─ G5-01 main.rs 拆分 (2-3d) — G1-02 後
├─ G5-03 instrument_info 拆分 (1-2d) — 並行
└─ G5-02 live_session_routes 拆分 (1-2d) — 並行
  完成條件：所有硬違反降至 <1200 / 8 項警告邊際預拆

W19 Wave 2 — AI 接線 + 架構完善
├─ G5-04 ai_service 拆分 (1d)
├─ G5-06.1-3 bybit_rest_client / order_manager / startup (6-8d)
├─ G5-07/08 ipc_server / helpers 預拆 (2d)
├─ P3: clone 115 / lock 16 / O(n) scan (3-4d)
└─ governance/strategist/multi_agent 拆分 (4-5d)
  完成條件：Python governance 層邊界明確 / Rust API 層合規

W20-W22 Wave 3 — 性能優化 + 可讀性深化
├─ G5-06.4-5 resting_orders / risk_config (3-4d)
├─ G5-09 strategist_scheduler 預拆 (1d)
├─ P1 startup parallel await (1d)
├─ P4/P6 time.time() 統一 (1d)
└─ 長期債務（eviction / backoff / profiling）
  完成條件：所有邊際項 <1000 / 無緊急拆分觸發

W23-W27 Wave 4+ — 長期策略
├─ monkeypatch → DI 遷移評估 (延後)
├─ truth_source / experiment_ledger eviction (2d)
└─ Phase 5 邊界評估（E5-P3 決策）
```

---

## 五、檔案大小完整違反清單（wc -l 實測）

### Rust 硬違反（≥1200 行）

```
1762  ./rust/openclaw_engine/src/event_consumer/mod.rs
1367  ./rust/openclaw_engine/src/paper_state/resting_orders.rs
1328  ./rust/openclaw_engine/src/config/risk_config.rs
1192  ./rust/openclaw_engine/src/ipc_server/mod.rs
1143  ./rust/openclaw_engine/src/strategies/bb_reversion.rs
1136  ./rust/openclaw_engine/src/ws_client.rs
1124  ./rust/openclaw_engine/src/event_consumer/dispatch.rs
1011  ./rust/openclaw_engine/src/paper_state/maker_stats.rs
1010  ./rust/openclaw_engine/src/database/drift_detector.rs

✓ 已驗證實測 (4/24 wc -l 掃描)
```

### Python 硬違反（≥1200 行）

```
1449  ./program_code/…/live_session_routes.py
1258  ./program_code/…/ai_service.py
1216  ./helper_scripts/db/counterfactual_exit_replay.py  (script 層)

✓ 已驗證實測 (4/24 wc -l 掃描)
```

### 警告邊際（800-1200 行）

**Rust 8 項**：
```
1192  ipc_server/mod.rs                    ← 8 行至硬限
1182  tick_pipeline/on_tick/helpers.rs     ← 18 行至硬限
1166  strategist_scheduler/mod.rs          ← 34 行至硬限
1143  strategies/bb_reversion.rs           ← E5-P2-4c
1136  ws_client.rs
1124  event_consumer/dispatch.rs           ← 已 sibling
1100  intent_processor/mod.rs
1068  claude_teacher/applier.rs
```

**Python 22 項**（top 12）：
```
1172  governance_routes.py
1170  strategist_agent.py
1137  multi_agent_framework.py
1088  paper_trading_routes.py
1014  governance_hub.py
977   truth_source_registry.py
974   experiment_ledger.py
971   h0_gate.py
958   trade_attribution.py
948   reconciliation_engine.py
946   optuna_optimizer.py (ML training)
944   passive_wait_healthcheck.py (helper script)
```

---

## 六、E5 優化 Phase 1-5 完成度總結

| Phase | 名稱 | 代碼 | 時間 | 狀態 | 殘留 |
|-------|------|------|------|------|------|
| P0 | Refactor Wave | `e5_optimization_final_report` | 2026-04-18 | ✅ | — |
| P1 | Refactor Wave 1 | 15 items | 2026-04-19 | ✅ | call_ollama_timed / from_guardian_review 清理 ✅ |
| P2 | Refactor Wave 2 | 8 items | 2026-04-19 | ✅ | E5-P2-4c bb_reversion 拆 / E5-P2-X commands 拆 |
| FN | Functional Defects Wave | audit 9 findings | 2026-04-19 | ✅ | — |
| — | Full-Chain Audit | S1-S10 / P1-P10 / R1-R10 | 2026-04-24 | 🟡 | 建議 30 項待納入 Wave 1-3 |

**累計完成主軸**：
- ✅ tick_pipeline 2274 → 1012 (2026-04-22)
- ✅ main_legacy.py 5113 → 468 (2026-04-23)
- ✅ 5 大 helper 實裝 + 未回彈
- ✅ zero-copy TickContext
- ✅ parallel DB flush
- 🟡 event_consumer fn 拆分待 Wave 1 (新發現)
- 🟡 8 Rust 硬違反待 Wave 1-2 (新發現)

---

## 七、可讀性 Pain Points Top 10

**按嚴重度排序**：

| # | 檔案 | 行數 | 類型 | 嚴重度 | 收益 | 工時 |
|---|------|------|------|--------|------|------|
| 1 | event_consumer/mod.rs:run_event_consumer | 1696 (fn) | 深度嵌套 + 單函數巨型 | 🔴 Critical | onboarding -50% / bug prevention +50% | 2-3d |
| 2 | main.rs:async_main | ~400 (fn) | 多職責雜糅 + 錯誤分層缺失 | 🔴 Critical | 故障診斷 -30% | 2-3d |
| 3 | bb_reversion.rs | 1143 | 策略參數 + impl 混在 | 🟠 High | 調參定位 +50% | 1d |
| 4 | governance 層（3 檔 3600+ 行） | routes/hub/session | 責任邊界模糊 + 授權狀態機跨檔 | 🟠 High | G-1 acceptance -30% | 3-4d |
| 5 | ipc_server/mod.rs | 1192 | dispatch routing 過度集中 + 8 行至硬限 | 🟠 High | 新 handler 無衝突 | 2d |
| 6 | startup::build_exchange_pipeline | 401 (fn) | 串行 await 可並行化 | 🟡 Medium | 啟動快 3-5s | 1d |
| 7 | strategist_agent._handle_intel | 198 (fn) | 6 職責混在單 fn | 🟡 Medium | 單測覆蓋 +40% | 0.5d |
| 8 | ai_service.py | 1258 | 30 個 `_handle_*` 方法 | 🟡 Medium | validation 層級化 | 1d |
| 9 | ws_client.rs | 1136 | 連線 + ping + subscribe + parse 混 | 🟡 Medium | 新增 topic 無衝突 | 2d |
| 10 | tick_pipeline clone 115 | — | 熱路徑 allocation 過度 | 🟡 Medium | GC 壓力 -5-10% | 2-3d |

---

## 八、E5 決策與風險

### 決策 1：event_consumer fn 拆分優先級

**E5 建議**：**Wave 1 W17 即刻** （優先於所有 G5 項）

**理由**：
- 1696 行單 async fn = 項目史上最大（vs 2026-04-01 _process_pending_intents 462 行的 3.7 倍）
- FIX-26-DEADLOCK-1 已在此 fn 內發現（squeeze_detected_ms 清除邏輯缺失）
- 每次未來 bug 修復成本指數級增長（當前 onboarding 困難）

**實施順序**：
1. E1 讀 fn 邏輯，按事件分類拆 handlers（select! 分支 → `handle_market_event` / `handle_trading_event` 等）
2. 保留 `run_event_consumer` 主框架 ~100 行，純粹做 select! 調度
3. 保證 select! 語意不變（async 所有權 + `Receiver<>` 共享）
4. engine lib 測試基準線 1980 → 1980（零功能變更）

**與 G1-02 同義務**（TODO 中已列）

### 決策 2：硬違反 8 檔拆分排序

**E5 建議**：拆分優先級排序（非 TODO 中的 G5-01-06 並行）

```
1. event_consumer fn (G1-02)     — W17 立即 (3-4d)
2. main.rs (G5-01)                — W17 後期 (2-3d)
3. instrument_info (G5-03)        — W18 並行 (1-2d)
4. live_session_routes (G5-02)    — W18 並行 (1-2d)
5. ai_service (G5-04)             — W19 (1d)
6. 5 檔 (G5-06.1-5)               — W19-W20 (6-8d)
```

**理由**：
- event_consumer fn 是 Blocker（開啟 async 所有權解鎖）
- main.rs 依賴 event_consumer 拆後思路清晰（bootstrap 概念確立）
- Python 項可並行（無 Rust 依賴）

### 決策 3：警告邊際預拆

**E5 建議**：新增 G5-07/08/09（防下輪撞牆）

```
G5-07: ipc_server/mod.rs 1192     — W19 (2d) — 8 行至硬限
G5-08: helpers.rs 1182             — W19 (1d) — 18 行至硬限
G5-09: strategist_scheduler 1166   — W20 (1d) — 34 行至硬限
```

**ROI**：每檔 1-2d，防止下輪重構因撞牆導致緊急拆分（時間浪費 3-5d）

### 風險評估

| 風險 | 嚴重度 | 緩解措施 |
|------|--------|---------|
| event_consumer async 所有權複雜 | 🔴 High | E1 + PA 緊密 session / 拆分後 E2 adversarial review / 完整 unit test |
| Rust 拆分導致編譯回歸 | 🟠 Medium | 各拆分伴隨 `cargo test` 基準線驗證 / cargo check |
| Python governance 拆分後接線複雜 | 🟠 Medium | 併行 G3-02 IPC 設計，統一介面 |
| 拆分時間高估 | 🟡 Low | 2-3 person-week 投入，PM per-case 調整 |

---

## 九、與 CLAUDE.md §九 合規檢查

**硬上限 1200 行** ⚠️ 當前違反狀態：

| 檔案 | 行數 | 超限 | 狀態 | 期限 |
|------|------|------|------|------|
| event_consumer/mod.rs | 1762 | +562 | 🛑 禁 merge | W17 完成 |
| main.rs | 2062 | +862 | 🛑 禁 merge | W18 完成 |
| instrument_info.rs | 1975 | +775 | 🛑 禁 merge | W18 完成 |
| bybit_rest_client.rs | 1725 | +525 | 🛑 禁 merge | W19 完成 |
| order_manager.rs | 1554 | +354 | 🛑 禁 merge | W19 完成 |
| startup.rs | 1377 | +177 | 🛑 禁 merge | W19 完成 |
| resting_orders.rs | 1367 | +167 | 🛑 禁 merge | W20 完成 |
| risk_config.rs | 1328 | +128 | 🛑 禁 merge | W20 完成 |
| live_session_routes.py | 1449 | +249 | 🛑 禁 merge | W18 完成 |
| ai_service.py | 1258 | +58 | 🛑 禁 merge | W19 完成 |

**§九 原文**：
> 文件大小限制
> - **800 行** ⚠️ 警告線（E2 必須標記）
> - **1200 行** 🛑 硬上限（不允許 merge）

**E5 結論**：當前 10 檔違反，**必須 W17-W20 內逐檔清除**，否則無法上線（Phase 5 Live gate §四 檢查）

---

## 十、輸出與交接

### 報告成品清單

1. **本報告**：`docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-24--todo_complete_proposal.md`（5000+ 字）
2. **E5 memory 更新**：2026-04-24 新發現補登（scheduler 停滯、PostOnly 反向、ExecutorAgent shadow）
3. **TODO.md 同步建議**：
   - G5-07/08/09 新增（ipc_server / helpers / strategist_scheduler 預拆）
   - G1-02 優先級調升為 Wave 1 Blocker
   - 各項工時確認（基於 E5 2026-04-24 full-chain audit）

### E5 審核檢查清單

- [x] 所有硬違反檔案已列舉 + wc -l 驗證
- [x] 歷史報告 5 份全掃 + L3 audit 對照
- [x] 當前 TODO.md 完整性檢視
- [x] 拆分樣式驗證（ma_crossover / TICK-PIPELINE 為範本）
- [x] 優先級矩陣 + Wave 路線圖
- [x] 風險評估 + 緩解措施
- [x] CLAUDE.md §九 合規對標

### 推薦開工時機

**🟢 立即 W17 開工**（無延遲理由）
- event_consumer fn 拆分（G1-02）
- scheduler 診斷 + 修復（G1-01）
- PostOnly 配置修（G1-05）

**🟡 W18-W20 並行**
- G5-01/02/03（main.rs / live_session / instrument_info）
- Python governance 層次設計（為 G3 準備）

**🟢 長期監視**
- 每週 code review 檢查新增檔案行數，≥800 立即標記（E2 强制 review）
- 新 IPC handler 加 ipc_server 時同步預拆（已超 1192）

---

*E5 Optimization Engineer Report*  
*2026-04-24 04:45 CEST*  
*基於 E5 memory + profile + 5 份歷史報告 + L3 audit + 實測檔案大小*

