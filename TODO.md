# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-10（DB fresh-start reset · 乾淨數據重新起算）
測試基準線：**Rust engine lib 872 · Python control_api 2427 passed (1 pre-existing fail · 1 skipped) · ml_training 135 passed (6 skipped)**

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> 歷史歸檔索引在文件末尾。詳細完成度視角見 README.md。

---

## 🎯 當前焦點（按執行順序）

### 1. 🟢 觀察期 — 等數據（無開發動作，只需維運）

Phase 5 cost_gate 改造已全部上線。現在唯一阻擋正式 Live 的是**時間**：乾淨 paper 數據累積。

- [ ] **PH5-VERIFY-1** 7d paper observation — 看 fills / realized pnl 分布是否改善
  - **重新起算**：2026-04-10 DB fresh-start reset（71.3M 開發噪音清除），乾淨數據從今天開始
- [ ] **JS 滾動重跑排程**（2026-04-10 = Day 1）
  - 2026-04-11（Day 2）：`python3 -m program_code.ml_training.james_stein_estimator --days 2`
  - 2026-04-12（Day 3）：`--days 3`
  - 2026-04-17（Day 7）：`--days 7`
  - 之後每週拉長窗口（14d → 30d）直到估計穩定
  - 若某 cell 轉正 → 重啟引擎後 mode-aware gate 自動對該 pair 生效
  - `settings/edge_estimates.json` 更新後需重啟引擎才生效（無 hot-reload）
- [ ] **LG-1** Paper Trading 穩定運行 21 天（Live Gate 前置）

---

## 🛡️ Live 前必做（SEC 安全 + 告警基礎設施）

### 安全（架構性，必做）

- [x] **SEC-05** GUI `innerHTML` XSS ✅ — ocEsc() 全量包裹
- [x] **SEC-17** `OPENCLAW_ALLOW_MAINNET` 移除 ✅ — API key 填入 = 唯一上線條件
- [ ] **SEC-08** IPC socket 無認證（Live 前必做）
- [ ] **SEC-21** Cookie `secure=True`（HTTPS 上線後）
- [ ] **SEC-04 / 06 / 13** 深度 E3 審查（4 項）
- [ ] WP-CC/FS-1 / BI-1 / P9 / SM-1（4 項 CC）

### 告警通道

- [ ] **OC-3** 多通道分級告警（P0→緊急群 / P1→常規群）— **阻塞 6-RC-6**
- [x] Phase 6 自動降級動作層完成（6-RC-1~5,7,8,9,10）✅

---

## 📈 Phase 6 — 漸進放權 + Reconciler 自動收縮（W19-20）

### 6-RC（Reconciler 自動 governor 動作層）

- [x] **6-RC-1** 動作通道隔離 ReconcilerEscalate/DeEscalate ✅
- [x] **6-RC-2** V014 event_type 隔離 ✅
- [x] **6-RC-3** 動作策略（MajorDrift→Cautious / burst→CB+CloseAll）✅
- [x] **6-RC-4** 自身冷卻（per-symbol 30min + 全局 5min + hybrid 恢復）✅
- [x] **6-RC-5** Per-symbol minQty dust floor ✅
- [ ] **6-RC-6** 多通道告警 + 15s 介入窗口 ⚠️ 阻塞於 OC-3
- [x] **6-RC-7** 整合測試（7 場景 reconciler_e2e.rs）✅
- [x] **6-RC-8** Live blocker 解除 ✅
- [x] **6-RC-9** Baseline staleness 政策 ✅
- [x] **6-RC-10** REST 失敗升級（≥10 次→Cautious）✅

### 6-Phase（漸進放權 + 驗收）

- [ ] 6-01~03 漸進放權管線 + 畢業邏輯 + Live 審批
- [ ] 6-04~06 全管線回放 + 壓測 + sync_commit Live 驗證
- [ ] 6-07~08 EvolutionEngine deprecated + 文檔
- [ ] 6-09~13 E2 + E4 + QA 端到端 + E5 + PM

---

## 🚦 Live Gate（前置：Phase 6 + 21 天 paper + Alpha > 0）

- [ ] LG-1 Paper Trading 穩定運行 21 天（同觀察期）
- [ ] LG-2 H0 Gate blocking 驗證（shadow → blocking）
- [ ] LG-3 provider pricing table 正式綁定
- [ ] LG-4 M 章 Supervised Live Gate
- [ ] LG-5 N 章 Constrained Autonomous Live

**完成後**：換入 mainnet API key，系統即進入真實 Live（零代碼改動）。

---

## 📈 Phase 5 補強（非阻塞，觀察期後評估）

WIRE-0/WIRE-1 + DL-1/DL-2 + JS-1 + 5-01~03 已全部 ✅。下面是原 backlog 精度提升項：

- [ ] 5-04~07 DL-1 Symbol Embedding + DL-2 Regime LSTM Shadow
- [ ] 5-08~09 JS+Scorer 整合 + correlation_pairs
- [ ] 5-10~13 E2 + E4 + QC + E5

---

## 🧰 WP Backlog（低優先 · 維護性）

詳細子項見 `docs/audits/2026-04-06_consolidated_remediation_report.md` §10。

### WP-F GUI（P2 ~10 項）

- [ ] WP-F/D-01 applyAIAdvice() 只 toast 無實效
- [ ] WP-F/UX-06 Submit 無 loading 狀態
- [ ] WP-F/UX-07~10 術語統一（Paper/Live/Session 各 Tab 標籤）
- [ ] WP-F/AH-05 Apply 標籤誤導
- [x] WP-F/AH-06 Risk-tab dirty-tracking ✅
- [ ] WP-F/O-xx / AH-08~11（詳見 §10.1）
- [ ] `preferred_margin_mode` / `preferred_position_mode` GUI 入口

### WP-E4 測試覆蓋（13 項）

- [ ] T-P2-5 rest_poller / T-P2-6 quality_writer / T-P2-9 PyO3 bridge tests / T-P2-10 panic-path / T-P2-11 並發
- [ ] T-Q3/Q4/Q7/Q8 覆蓋品質
- [ ] T-I1~I4 tarpaulin / CI 門禁 / 文檔
- [ ] WP-E4/T-P1-1 殘餘 event_consumer 完整事件循環整合測試

### WP-E5 大文件

- [ ] tick_pipeline.rs 2117 行 — 留專屬 session
- [ ] governance_hub.py 1927 行 — 拆分需獨立 sprint + E2+E4

### WP-I 文檔衛生

- [ ] R4-NAME-1 / R4-MEM-1 / R4-REF-ST-1

---

## 📦 殘留延後（前 phase，非阻塞）

- [ ] 2-11 actual training（需足夠 trading.fills 累積）
- [ ] ort crate activation（首個 ONNX 模型訓練後）
- [ ] 4-06 LinUCB live warm-start deployment（script 已交付，等首次 v1→v2 遷移）

### Phase 4-Conditional（觸發後）

- [ ] 4-1 PairsTrading（需 3 月協整）/ 4-2 Beta Hedging / 4-3 Kalman / 4-5 Mac Studio 遷移 / 4-10 Jump detection

### 長期整合（非緊急）

- [ ] OC-4 MCP PostgreSQL 自然語言查詢
- [ ] OC-5 FundingArb REST 資金費率輪詢

---

## 📚 已完成歸檔索引

- **Live GUI P0~P6 + DEAD-PY-1/2 + 1C-4 收尾**：`docs/archive/2026-04-10--completed_todo_live_gui_dead_py.md`
- **Phase 5 P0 promotion + WIRE chain**：commits `5d7d673` → `0e848fa` → `638afa3` → `563d54a` → `5e760be`
- **ARCH-RC1 Session 1A → 1C-4 WRAP**：`docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md` + `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`
- **Phase 4 (4-00 ~ 4-21 + 4.1)**：`docs/audits/2026-04-07_phase4_final_signoff_audit.md`
- **Session 11 之前**：`docs/worklogs/phase5_arch_rc1/2026-04-06--completed_todo_archive_l3_phases.md`
- **Phase 0/1/2/3 + Rust migration**：`docs/worklogs/phase5_arch_rc1/2026-04-04--completed_todo_archive_phase0123_rust.md`
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
