# FA Wave 3 Spec Readiness 審計

**審計日期**：2026-04-26 CEST
**審計員**：FA (Functional Auditor)
**審計範圍**：TODO.md 第 275-313 行 Wave 3 全部 14 項 + 對照 22 份治理文件 + 上輪 4-24 全鏈審計

---

## 評級表

| ID | 完成標準（從 TODO 抄） | spec readiness | E1 可開工？ | 缺失 spec 項 |
|----|---------------------|----------------|-----------|-------------|
| **EDGE-P3** | clean ≥200 + per-strategy CI lo>0 + orphan_frozen clean ≥20 + healthcheck [11] 連 3d PASS | **B** | **條件 Y** | (1) Gate 1 fallback 部署後**回滾劇本**未明確（雖 IPC 熱重載可，但 trigger 條件未寫死）(2) per-strategy bootstrap CI 計算方法選定（QC 在做，PA 整合）(3) 4 條件全 ALL 滿足才 trigger 的**自動 vs 手動 gate 機制**未寫；TODO 寫 "auto-gated by check [11]" 但其他 3 條件如何 cascade 缺驗收清單 |
| **EDGE-P1b** | exit_features 累積 ≥1w + 7 維閾值 bind | **C** | **N** | **核心 spec 缺**：(a) 7 維閾值是哪 7 維？目前無清單（猜測：phys_lock_giveback_atr_norm / micro_profit / shadow / atr_pct / fee_rate / signal_strength / regime_complexity，但無權威定義）(b) bind 動作的 contract — 是 cost_gate 加一條 condition？還是 ExitConfig 新欄位？(c) ≥1w 累積後是按 row count 還是 N hours data fresh？ MIT 並行做但 spec 未寫 |
| **EDGE-P2-flip** | shadow flip + P1-10 並行 | **C** | **N** | **核心 spec 缺**：(a) shadow flip 的 acceptance criteria 未量化（healthcheck [15] 提到 "Python vs Rust decision agree rate ≥95%" — 是這個嗎？需 PM/QC 確認）(b) flip 步驟 SOP — 改 ExitConfig.shadow_enabled 還是 IPC patch？回滾路徑？(c) "P1-10 並行" 含義模糊：是 flip 期間繼續觀察 P1-10 PostOnly 數據？還是同時做 P1-10 結案？ |
| **G2-01** | PostOnly 1-2w 驗收：fee drop ≥60% 或決策策略下架 | **A** | **Y** | spec 完整 — 但驗收的 "fee drop ≥60%" baseline 的 "原始 fee" 數值需明確（G7-09 fix 才開始混 maker/taker，pre-fix 全 5.5bps；推 baseline = 5.5bps，post = ≤2.2bps，passive 等到 ~05-07~08；FA 標 ✅ 因 healthcheck [3] maker_fill_rate 已存在） |
| **G2-02** | ma R:R counterfactual ≤1.5× 或 SL/TP Option B 定制 | **B** | **條件 Y** | (1) "Option B" 在 `EDGE-P2-3` 等 backlog 提到但定義散落各處（推測 = 策略層 SL/TP 而非全局；G2-03 才是落地）(2) counterfactual 報告由 P0-3-01 也寫，重疊但範圍不同 — G2-02 限 ma_crossover，P0-3 全策略（spec 衝突嗎？）(3) ≤1.5× R:R baseline 量化 — 當前 G1-04 baseline 顯示 ma_reverse 0.45🔴（已 < 1.5× 但是 Risk:Reward 倒置，不是 R:R ≤1.5× 想表達的含義）— **需 QC 對齊 R:R 定義** |
| **G2-03** | ma SL/TP Option B 定制 | **C** | **N** | **核心 spec 缺**：(a) Option B 是「策略覆蓋 P1 max 硬頂以下的軟值」還是「strategy_params.toml 加 sl_atr_mult / tp_atr_mult per-strategy」？memory `project_agent_p2_dynamic_sl_tp.md` 提到 Agent 可 adjust 但 P1 max 是硬頂，G2-03 要在哪一層改 unclear (b) 與 G2-02 counterfactual 結論的 binding 邏輯：counterfactual 出 R:R 1.6 時，G2-03 自動改成 1.5 還是手動拍腦袋？ (c) 涉 strategy 層改動需先寫 RFC（類似 G3-01 PA 755 行 RFC 模式） |
| **G2-04** | Grid disable 決策會（若 PostOnly 後仍負 edge） | **A** | **Y**（會議性質，非寫碼） | spec 完整 — 決策會 1h，輸入 = G2-01 + P0-3 結果，產出 = decision log。**E1 不需開工**（PM+FA 主導）；標 A 但「派 E1」不適用 — PM 主持 |
| **G2-05** | bb rebuild 驗證 | **B** | **條件 Y** | (1) FIX-26-DEADLOCK-1 已在 binary（21:58 部署），rebuild 驗證實質為 healthcheck [12] 7d 觀察 (2) "驗證" 完成標準 — fill count > 0 / 7 d 仍 0 fills 觸發 G2-06 (3) 但 spec 缺：post-rebuild 後 N 小時無 fill 也 OK（squeeze 罕見）vs 7d 0 fills 確認 dormancy — 中間區間沒寫 |
| **G2-06** | bb threshold recal | **A** | **Y** | spec 已展開（觸發、範圍 a/b/c、避免項全寫）— TODO 第 294 行就是 PA 級任務書；E1 拿到 P1-11 Phase 1 sweep 工具 + spec 完整可直接開工。前置 G2-05 結論為 dormancy（資料條件） |
| **G8-01** | e2e 認知自適應 80+ coverage | **B** | **條件 Y** | (1) "認知自適應" 範圍：CognitiveModulator + DreamEngine + OpportunityTracker（H3 列為 0 引用模組）— 是測 Python `CognitiveModulator` 實作（哪個？）還是 G3-06 LayerEscalationConfig？(2) 80+ coverage 指 line coverage 還是 functional coverage？(3) 前置 G3-04 已完成（`852da0f`），可重用；但 G3-06 Phase A 完 / Phase B Rust integration deferred — 完整 e2e 卡在 G3-08 Layer 2 toolkit |
| **G8-02** | Py↔Rust parity ≥95% | **A** | **Y** | spec 量化清楚（decision agree rate ≥95%）+ healthcheck [15] 已實裝 + EDGE-P2 flip 完整接通；測試骨架可重用 G3-04 e2e + healthcheck `shadow_exit_agreement_phase2`。E1 直接開工 |
| **G8-03** | 灰度驗收自動化（shadow metrics） | **B** | **條件 Y** | (1) "灰度" 流程未明確：staged rollout 機制（10% → 25% → 50% → 100%）vs simple shadow→live flip（後者已 G3-04 e2e 過）(2) "shadow metrics" 列表：agree_rate / decision_lag / pnl_diff — 需 QA 整理；EDGE-P2 flip 是首次落地，可重用其 metric set (3) automation 要 cron 還是 GUI button？ |
| **G8-04** | healthcheck DAG 線性化 | **A** | **Y** | spec 清楚：當前 17 check 之間隱藏依賴（如 [13] FAIL 時 [11] 必 FAIL；[1] FAIL 時 [3]+ 全失效）→ 線性化 = 顯式 dependency graph + cron 順序 + skip-downstream-on-FAIL 邏輯。1d 工時合理。E1 直接開工，QA review |
| **G8-05** | AI cost ROI 面板 | **B** | **條件 Y** | (1) 前置 G3-09 是 `cost_edge_ratio` 演算法（P3 deferred 至 Wave 3+），未完成則 G8-05 缺 backend metric source (2) "AI cost ROI" 面板的 metric set：daily_call_count / daily_cost / per-strategy_attribution / cost_edge_ratio gauge — 需 PM 列定義 (3) GUI 位置：tab-overview / tab-strategy / new tab? 需設計 |

## 評級分布

- **A 級（5 項）**：G2-01 / G2-04 / G2-06 / G8-02 / G8-04
- **B 級（6 項）**：EDGE-P3 / G2-02 / G2-05 / G8-01 / G8-03 / G8-05
- **C 級（3 項）**：EDGE-P1b / EDGE-P2-flip / G2-03

---

## 立即可派 E1 清單（A 級）

1. **G2-06 bb threshold recal** — sweep tool ready + 完整 spec + 前置 G2-05 觀察自然觸發；2-3d 工時
2. **G8-02 Py↔Rust parity test ≥95%** — healthcheck [15] 在 + G3-04 e2e 可重用；1-2d 工時
3. **G8-04 healthcheck DAG 線性化** — 17 check 列表清晰 + 1d 工時 + QA 一輪 review
4. **G2-01 PostOnly 驗收** — passive 等 ~05-07/08（非 E1 寫碼，FA+QC 收 healthcheck [3] 數據）
5. **G2-04 Grid disable 決策會** — 會議性質非 E1 開工（PM+FA 主持）

## 需先補 spec 清單（C 級）

1. **EDGE-P1b 7 維閾值 bind** — 必須先寫：
   - PA 級任務書定義 7 維清單（推測：giveback_atr / micro_profit_bps / atr_pct / shadow_enabled / fee_rate / signal_strength_gate / regime_complexity）
   - bind contract（cost_gate condition vs ExitConfig 新 flag）
   - ≥1w 累積的測量定義（row count vs hours of fresh data）
2. **EDGE-P2-flip shadow flip** — 必須先寫：
   - flip acceptance criteria（≥95% agree rate? 多久觀察？）
   - flip 步驟 SOP + 回滾機制
   - "P1-10 並行" 範圍釐清
3. **G2-03 ma SL/TP Option B 定制** — 必須先寫：
   - Option B 定義 RFC（類似 G3-01 PA 755 行模式）— 哪一層改？strategy params or risk_config?
   - G2-02 counterfactual 結論 → G2-03 binding 邏輯（自動 vs 手動）
   - P1 max 硬頂 vs 策略軟值的 boundary

---

## 治理文件 vs 實作 gap

對照 SPECIFICATION_REGISTER.md（22 份 Active spec）+ Wave 3 內容，識別 **未在 TODO 對應**的潛在 spec gap：

1. **DOC-04 Agent Learning Evolution（tier advancement criteria）** — Wave 3 G2 沒涵蓋 EX-05 learning_tier_gate.py 的策略晉升標準。當前 STRATEGIST-AUTO-PROMOTE 在 Backlog 標 P3 deferred（"P2-01 穩定後"）。Wave 3 PostOnly 結果 + bb rebuild 結果應觸發 tier 重評，但 TODO 無對應條目 → **建議追加 W3 子任務或明確延至 W4**

2. **EX-04 Reconciliation Engine** — Wave 3 EDGE-P2-flip 涉及 Python↔Rust decision agree，與 EX-04 paper vs live/demo position consistency 重疊。但 TODO G8-02 只測 decision parity，未測 reconciler 在 shadow→live 過程的對賬影響 → **G8-02 spec 應明確包含 reconciler 路徑**

3. **DOC-08 Incident Response §12** — 16 條根原則沒有專條 spec，但 G2-04 Grid disable 決策會其實是**安全不變量**事件響應（"failure default 收縮" 原則 #6 觸發路徑）；建議把 G2-04 結果 → DOC-08 incident log 鏈路寫進完成標準

4. **SM-02 Decision Lease State Machine** — 上輪審計 FA-2026-04-24-C3 揭露 Rust 真實交易路徑 0 觸發 Lease；Wave 3 G3-08 H1-H5 → Rust IPC Gateway（P3 deferred）才會處理。但 EDGE-P2-flip 觸發後 Python 5-Agent shadow→live 還是要走 acquire_lease → 應在 EDGE-P2-flip 完成標準明確 Lease state 觀察

5. **DOC-03 Market Regime Detection** — G7-03 Phase B 已 wire 3 策略（bb_breakout / ma_crossover / bb_reversion），grid_trading deferred。Wave 3 G2 系列（特別是 G2-02 ma counterfactual）應對齊 regime-aware 評估，但 TODO 未明確要求 → **建議 G2-02 完成標準加 "per-regime R:R 切片"**

---

## 關鍵風險與建議

1. **C 級 3 項全卡在 Wave 3 早期**（EDGE-P1b 滿週期 2026-04-26，EDGE-P2-flip 等 P1b，G2-03 等 G2-02）— 須在 W3 啟動前 2-3 天派 PA 並行寫 spec，否則 W3 中段會卡死等 spec
2. **Wave 3 缺「策略晉升」對齊**（G2-04 Grid disable 是降級，但 G2-01 PostOnly 成功的策略無對應 promote/tier 檢查條目）
3. **healthcheck DAG（G8-04）排序在 W3 末**，但 17 check 隱藏依賴在 W3 早期（G2-01 / G2-05 觀察期）已產生 false PASS/FAIL 風險 — **建議 G8-04 提前到 W3 第 1 週**

---

## 派發建議（給 PM）

| Wave 3 派發批次 | 任務 | 角色 |
|---|---|---|
| **W3 立即（5/22）** | G2-06 / G8-02 / G8-04 | E1 並行 |
| **W3 立即補 spec** | EDGE-P1b / EDGE-P2-flip / G2-03 spec RFC | PA 主寫 + FA + QC review |
| **W3 第 1 週** | G2-02 counterfactual（前置 EDGE-P2 結果） | QC + FA |
| **W3 第 2-3 週** | G8-01 / G8-03 / G8-05 | E1 + QA + AI-E |
| **W3 passive** | G2-01 / G2-05（healthcheck 自動） | FA + QC 收數 |
| **W3 末（會議）** | G2-04（若 G2-01 fail） | PM + FA |

---

## 關鍵檔案路徑

- `srv/TODO.md`（Wave 3 第 275-313 行）
- `srv/docs/governance_dev/SPECIFICATION_REGISTER.md`
- `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-24--full_chain_audit_report.md`
- `srv/docs/CCAgentWorkSpace/FA/profile.md`
- `srv/docs/CCAgentWorkSpace/FA/memory.md`

---

**FA AUDIT DONE** — 2026-04-26 CEST
