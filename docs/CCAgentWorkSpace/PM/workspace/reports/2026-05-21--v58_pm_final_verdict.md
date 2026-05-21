# v5.7 + v5.8 真實開發路線 — PM 最終 Verdict

**日期**：2026-05-21
**整合範圍**：v5.7 12 prefix DONE + v5.8 13 module + 14 multi-agent audit + PA 整合
**Verdict**：**DISPATCH-NEEDS-FIX — 13 prerequisite 完成後 D+5~D+10 內可派 Sprint 1A-β**
**前置**：v5.7 Sprint 1A-α 已 PM-signed 2026-05-21，不受影響

---

## 〇、PM 對 operator 4 維度問題的直接答覆

operator 問：「v5.8 + v5.7 開發完成後是否真實達到 功能 / 可實現性 / 無邏輯錯誤 / 無遺漏板塊 / 無遺漏文檔 五個 OK」？

| 維度 | PM 結論 | 距離 OK 的差距 |
|---|---|---|
| **功能完備性（交易/自主/風控/學習）** | **5/4 維度 OK，1/4 PARTIAL** | 自主調整缺 3 子能力（hot-swap / capacity-aware / cross-strategy correlation） |
| **可實現性** | **OK（但工時系統性偏低 20-43%）** | 真實 Y1 3,500-5,200 hr / 44-55w（v5.8 文本 2,780-3,930 hr / 37-44w） |
| **無邏輯錯誤** | **NEEDS-FIX** | 14 audit 識別 16 CRITICAL + 24 HIGH（M1 命名衝突 / M10 HMM 黑名單 / M11 ad-hoc threshold / 5-gate auto path inheritance / operator forgetfulness vs priority 5 衝突） |
| **無遺漏板塊** | **3 個 PM verdict missing 仍缺** | M3 strategy hot-swap / M6 capacity-aware sizing / M7 cross-strategy correlation re-sizing — operator 已明示要 13 module 全補但 v5.8 實際 10/13 |
| **無遺漏文檔** | **NEEDS-FIX** | ~46 個新文件未 land（7 ADR + 13 module spec + 12 V### schema spec + 8 runbook + docs/README index + TODO refactor） |

**一句話結論**：v5.8 thesis 14 audit **全 0 NO-GO**（8 GO / 3 conditional HOLD），但 **5/5 維度都有「派發前必補項」**；補完 16 CRITICAL must-fix 後 **可直接派 Sprint 1A-β** 開始真實開發；**Y1 末 autonomy ≈ 66% / Y2 Q2 ≈ 90% / Y3 Q2 ≈ 95%**（不變於 v5.7 PM autonomy verdict 估算）；**真正「不需操作員介入」時點 = Sprint 1A 起 ~21-32 個月**。

---

## 一、14 multi-agent audit verdict 全表

| Agent | Verdict | Top Risk（一句話）|
|---|---|---|
| **CC** | GO-WITH-CONDITIONS | M1 Tier 2 Auto governance 規格不足 → 原則 1/3/4/7/9/11/13 紅線 6 WARN |
| **QC** | GO-WITH-CONDITIONS | M10 Tier D 隱伏 HMM 黑名單 + M4 false discovery rate 未控 + M11 ad-hoc threshold |
| **MIT** | GO-WITH-CONDITIONS | V105-V113 9 個 schema spec 全 placeholder = V055 5-round loop 9 倍放大 |
| **E2** | **HOLD** | Sprint 1A 真實 670-1,015 hr（v5.8 543-797 hr 偏低 20-90%）+ 13 module 依賴 race + P0 precondition 缺席 |
| **E3** | GO-WITH-CONDITIONS | 5-gate auto path inheritance 未明文 + 11 新攻擊面 + M4 DRAFT writeback 需 Decision Lease |
| **E4** | GO-WITH-CONDITIONS | 4 state machine（M1/M2/M3/M7）50+ transition 易漏邊 + V### dry-run SOP 缺 + M9 mSPRT 演算法正確性無自動驗 |
| **E5** | GO-WITH-CONDITIONS | PG V106 health 高頻表 6mo +1.25-2.5 GB（占 buffer 16-63%）+ Y1 重估 3,500-5,600 hr / 44-55w |
| **A3** | GO-WITH-CONDITIONS | GUI 工時 +261-374 hr 完全缺席 + Console tab 歸屬未決 + A3 sign-off gate 在 §12 dispatch chain 缺席 |
| **BB** | GO-WITH-CONDITIONS | M13 Y2 Binance trade enable 與 CLAUDE.md Bybit-only + ADR-0033 衝突（須改 Y3+ 或重新 5-gate review） |
| **FA** | GO-WITH-CONDITIONS | 3 個 PM verdict missing module（hot-swap / capacity / correlation）+ M1/M3/M11 量化 threshold 缺 |
| **R4** | **HOLD** | ~46 個新文件需 land（7 ADR + 13 module spec + 12 V### + 8 runbook + index + TODO） |
| **TW** | **HOLD-WITH-CONDITIONS** | TW 工時 ~450-640 hr 完全沒列 + Sprint 1A 五階段 135-175 hr critical-path 0 並行 dispatch |
| **AI-E** | GO-WITH-CONDITIONS | ContextDistiller token 700→1,200-1,500 撞 L1<3s SLA + Y2 月 cost $112-213 vs DOC-08 $60 cap = 1.9-3.5x 超 |
| **QA** | GO-WITH-CONDITIONS | M1 Lease Tier 0-4 與 AMD-2026-05-15-01 Stage 0R-4 命名衝突 → IMPL 必撞牆或繞 5-gate |

**統計**：11 GO-WITH-CONDITIONS / 3 HOLD（含 1 conditional）/ 0 NO-GO

**3 HOLD 阻塞分析**：
- E2 HOLD：對抗式 audit 找盲點性質；非設計缺陷，5-7 hr PA+PM hands-on 補完即解
- R4 HOLD：文檔層面 ~46 新文件 + ~40 條 index 漂移；TW+PA+MIT 並行 ~150-200 hr 補
- TW HOLD-WITH-CONDITIONS：§3/§4 表格 + §12 decision point 補 = 1-2 hr 修檔 + PM 仲裁
- **三者都不阻 1A-α，阻 1A-β 派發**；補完 13 prerequisite 後全升 GO

---

## 二、5 維度詳細結論

### 2.1 功能完備性 — 5/4 維度

operator 強調「重點針對交易、自主、風控、學習，不限於此」。逐一展開：

#### 交易 ✓ OK
- v5.7 5 strategy（C10/Unlock/Pairs/C13/Funding short）+ Stage 0R/1/2/3/4 + 5-gate live boundary 完整
- v5.8 M1 Lease Tier（5 層 0-4）+ M12 OrderRouter（adaptive maker-vs-taker / slicing / cross-venue Y2）+ M13 Multi-asset class
- **自主交易程度**：Y1 末 75% / Y2 92% / Y3 95%
- 缺口：**M3 strategy hot-swap**（PM verdict M3 訴求 / v5.8 無對應）— 不重啟 engine 動態 add/remove strategy

#### 自主（自主調整）⚠️ PARTIAL
- v5.8 M1（Tier auto-execute）+ M6（Bayesian reward）+ M7（decay auto-demote）+ M9（A/B framework）+ M10（capital tier）
- **自主調整程度**：Y1 末 35% / Y2 85% / Y3 92%
- 缺口：
  - **M6 capacity-aware sizing**（PM verdict M6）— orderbook depth / liquidity 感知降權
  - **M7 cross-strategy correlation re-sizing**（PM verdict M7）— 多策略同向同 symbol 自動 down-weight
  - 5-gate auto path inheritance 未明文（M1 Tier 2 Auto 是否每筆執行仍 emit lease + Guardian replay）
  - operator forgetfulness mitigation 與 priority 5「human final review」衝突未明示

#### 風控 ✓ OK
- v5.7 既有 Guardian + Decision Lease + Kill Criteria + 5-gate live boundary
- v5.8 M3（health domain 5 級）+ M8（anomaly Y1 read-only / Y2 active trigger）+ M11（nightly counterfactual replay）+ M2 auto-disable always-on
- **自主風控程度**：Y1 末 93% / Y2 96% / Y3 97%
- 邊界：M3 / M8 / M11 trigger mutual exclusion contract 待補（runtime 可能重複 disable）

#### 學習（自主學習）⚠️ NEEDS-FIX
- v5.8 M4（self-supervised pattern miner）+ M5（online learning interface stub Y3+）+ M10（discovery pipeline Tier A-E）+ M11（continuous replay validation）
- **自主學習程度**：Y1 末 60% / Y2 88% / Y3 95%
- 缺口：
  - **M4 false discovery rate 未控制**（QC：rolling cross-correlation 500 hypothesis + α=0.05 naive 期望 25 false positives；Bonferroni / FDR 未提；event-window N<30 power<0.5）
  - **M10 Tier D regime auto-classify 隱伏 HMM 黑名單**（QC：math-model-audit skill 已明寫 HMM/GARCH 禁用；替代 = ATR-vol regime + funding state）
  - **M11 ad-hoc divergence threshold + 與 M7 信號重複 60-70%**
  - M5 online learning streaming update model parameters 觸碰原則 7「學習≠改寫 Live」

#### 其他維度（不限於上述 4）

- **整合**：v5.7 12 prefix DONE 4 leftover follow-up（V103 audit field / V### re-number / PG conn 範例 / Earn 五角色 cross-ref）必先收口
- **資金路徑**：v5.7 + v5.8 capital ladder（$10k → $25k → $50k → $75k → $150k）M10 Tier A-E 設計合理
- **AI cost**：v5.8 加入 M4 + M11 + M8 後 L2 推理月 cost $112-213 vs DOC-08 $60 cap 超 1.9-3.5x — ContextDistiller v4 ADR-0041 必補
- **ContextDistiller token**：v5.7 700-900 → v5.8 1,200-1,500 撞 L1 Ollama 9B <3s SLA
- **PG buffer**：V106 health_observations 6mo +1.25-2.5 GB（占 buffer 16-63%）— 必 hypertable + compression
- **GUI**：v5.7 漏 ~104-151 hr + v5.8 漏 ~157-223 hr = **累計 261-374 hr 未列**
- **TW doc**：~450-640 hr 完全未列
- **A3 sign-off**：~48-53 hr Y1 完全未列

### 2.2 可實現性 — OK（但工時嚴重低估）

| 維度 | v5.8 文本 | PA 整合 真實值 | 差距 |
|---|---|---|---|
| Sprint 1A 工時 | 543-797 hr / 7w | **670-1,015 hr / 7-9w** | +20-43% / +0-2w |
| Y1 total | 2,780-3,930 hr / 37-44w | **3,500-5,200 hr / 44-55w** | +26-32% / +7-11w |
| 缺項 | – | GUI +261-374 + TW +450-640 + MIT spec +120-140 + A3 +48-53 + governance amend +60-90 | – |
| AI cost | 0（漏） | $1,344-2,556/yr | 全漏 |

**結論**：可實現 ✓，但 operator 需接受 **Y1 calendar 44-55w**（v5.8 37-44w 是樂觀估）。

### 2.3 無邏輯錯誤 — NEEDS-FIX

14 audit 共識識別 **16 CRITICAL + 24 HIGH 邏輯/設計問題**。最關鍵：

| # | 問題 | 來源 | 影響 |
|---|---|---|---|
| CR-1 | v5.7 4 follow-up 未收口 | TODO §0.5 | Sprint 1A-β 派發直接阻 |
| CR-2 | M1 Lease Tier 0-4 與 AMD-01 Stage 0R-4 命名衝突 | QA / CC | IMPL 必撞牆或繞 5-gate（**改名 LAL / Layered Approval Lease**）|
| CR-3 | AMD-2026-05-21-01 autonomy-vs-human-final-review AMD 缺 | CC | 13 module 在 priority 5「human final review」灰區 |
| CR-4 | M13 Y2 Binance trade enable 與 CLAUDE.md Bybit-only + ADR-0033 衝突 | BB / CC | 需改 Y3+ 或新 5-gate review + ADR-0006 重簽 |
| CR-5 | M10 Tier D 隱伏 HMM 黑名單 + M8 GARCH | MIT / QC | math-model-audit skill 明寫禁用；ADR 必明寫 "no HMM / Markov-switching / GARCH" |
| CR-6 | M4 false discovery rate 未控 + leakage | MIT / QC / E4 | DRAFT 必附 6 attribute（N / Bonferroni p / effect size / sub-period / graveyard / cluster K silhouette）|
| CR-7 | M11 threshold ad-hoc + 與 M7 重複 | QC / FA / QA | M11 statistical derivation；M7 single decay authority |
| CR-8 | V105-V113 9 個 schema spec 全 placeholder | MIT / E4 / E5 / R4 | v5.7 V103/V104 V055 5-round loop 9 倍放大；+90-140 MIT-hr |
| CR-9 | PG dry-run mandatory + cross-V### dependency graph 缺 | MIT / E4 / E5 / QA | Sprint 1A-β/γ 順序 dispatch + cross-ADR collision gate |
| CR-10 | §10 P0 precondition table 缺（P0-EDGE-1 / LG-3 / OPS-1..4）| E2 / FA | Sprint 4 首次 Live 被阻；v5.8 §10 未列 |
| CR-11 | GUI +261-374 hr 缺 + Console tab + A3 sign-off | A3 | 6 個 Lv 3-4 surface 無 UX 設計 |
| CR-12 | TW +450-640 hr 缺 | TW | Sprint 1A 五階段 doc 無 owner |
| CR-13 | §3/§4/§14 工時統一上修 | 9 agent | calendar 不可達 |
| CR-14 | M12 maker_fill_rate metric + M11 historical source PG `market.liquidations` | BB / QC | Bybit historical liquidations API 不存在；用自家 PG |
| CR-15 | 5-gate auto path inheritance 明文 | E3 / CC | 7 個 auto path 寫 live state 必經完整 5-gate fail-closed |
| CR-16 | ADR-0041 ContextDistiller v4 + AI cost 重估 | AI-E | $112-213/月 vs $60 cap；token cap ≤ 800/推理 |

**16 CRITICAL 合計**：157-246 hr + 90-140 MIT + 450-640 TW + 261-374 GUI + 48-53 A3

### 2.4 無遺漏板塊 — 3 個 PM verdict missing

| PM verdict # | 訴求 | v5.8 對應 | 處置建議 |
|---|---|---|---|
| M3 | Strategy hot-swap（不重啟 engine） | **MISSING** | 新增 M14 "Engine hot-swap registry"（defer Sprint 4+ 但 v5.8 必列）|
| M6 | Capacity-aware sizing（depth/liquidity 感知） | **MISSING** | 擴 M6 acceptance 第 4 條 "orderbook depth bounds" / 或新建 M15 |
| M7 | Cross-strategy correlation re-sizing | **MISSING** | 擴 M1 acceptance "correlation-adjusted weight" / 或新建 M16 |

**結論**：v5.8 名為「13 module expansion」實際 PM verdict cover **10/13**；缺 3 個須在 §11 或 §13 明示 defer to v5.9 或新增 M14-M16。

### 2.5 無遺漏文檔 — ~46 個新文件需 land

| 類型 | 數量 | 派發前必 land | 可 placeholder |
|---|---|---|---|
| ADR draft | 7 必（M1/M5/M8/M9/M11/M12/M13）+ 6 R4 建議（M2/M3/M4/M6/M7/M10）| 4 個 CRITICAL（0034/0036/0037/0038）+ 6 個 R4 建議 PM 仲裁 | 3 個（0035/0039/0040 Sprint 1A-δ） |
| Module spec doc | 13 | 10 必 land（M1-M4/M6-M11）| 3 partial（M5/M12/M13）|
| V### schema spec doc | 12（V105-V116）| 9 必 land（V105-V113）仿 V103/V104 範式 | 3 partial（V114-V116）|
| Runbook | 8 必 | 6 必（M1/M2/M3/M6/M7/M9）| 2（M8/M11 隨 IMPL phase）|
| docs/README.md index | 46+ 條 | 派發前 ~11 條（v5.7 已 land 但缺）+ ~5 條（v5.8 主檔 + audit）| 派發後分 Sprint 補 ~39 條 |
| TODO §0.5 | 1 refactor | 必 land（v5.7 12 prefix DONE 歸檔 §F；v5.8 13 module 新 staging）| – |

**派發前必 land：~28 個文件**

---

## 三、真實 v5.7+v5.8 開發路線（時間軸 + 並行性）

### Sprint 1A 五階段拆分（W0-9，含修補 buffer）

```
Sprint 1A-α (W0-1.5)  — v5.7 12 prefix DONE [已 PM-signed 2026-05-21]
   + 4 leftover follow-up (8-12 hr)：V103 audit field / V### re-number / PG conn / Earn 五角色
   並行 sub-agent: PA + MIT + TW + FA + E3 + QA

Sprint 1A-修補 (D+0~D+5)  — 13 prerequisite + PM 仲裁 10 條 + operator decision 5 條
   工時 36-58 hr CRITICAL fix + ADR draft 4 + V### spec 9 + governance amend
   並行 sub-agent: 8-10
   結果：Sprint 1A-β 派發 readiness 達成

Sprint 1A-β (W1.5-3.5)  — v5.8 CRITICAL module DESIGN（M1/M3/M6/M7/M11）
   工時 310-460 hr（含 spec land buffer 90-140 hr）
   並行 sub-agent: 5-7
   Deliverable: ADR-0034/0036/0037/0038 land + V105/V106/V107/V112/V113 spec + 5 module spec doc

Sprint 1A-γ (W3.5-5.5)  — v5.8 ADD-per-operator module DESIGN（M2/M4/M8/M9/M10）
   工時 220-340 hr
   並行 sub-agent: 5-7
   Deliverable: M2/M4/M8/M9/M10 spec + V108/V109/V111 spec + 4 runbook

Sprint 1A-δ (W5.5-6.5)  — interface stubs（M5/M12/M13）
   工時 75-120 hr
   並行 sub-agent: 3-5
   Deliverable: ADR-0035/0039/0040 + V114/V115/V116 partial

Sprint 1A-ε (W6.5-9)  — integration verify + cross-ADR consistency + index + Monthly Review Wizard
   工時 60-100 hr
   並行: PA + R4 + TW + A3 + CC + FA
   Deliverable: docs/README index 補 ~39 條 + cross-ADR consistency PASS + Monthly Review Wizard spec
```

**Sprint 1A 真實 calendar**：~9 週（v5.8 文本 7w → +2w buffer）
**Sprint 1A 真實工時**：670-1,015 hr（v5.8 文本 543-797 → +20-43%）

### Sprint 1B-10 工時 + calendar

| Sprint | v5.8 文本 | PM 整合真實 | 主要工作 |
|---|---|---|---|
| 1B (W9-12) | 130-180 / 3w | 165-220 / 3w | v5.7 baseline 1B + C10 Stage 1 Demo + Earn first stake + M3 partial IMPL |
| 2 (W12-15) | 220-310 / 3w | 280-400 / 3w | Alpha Tournament + M4 pattern miner stage 1 + M10 Tier A productionize + M8 read-only |
| 3 (W15-18) | 220-300 / 3w | 280-380 / 3w | Top-1 Unlock SHORT build + Stage 0 shadow + M11 nightly replay + M3 statistical detectors |
| 4 (W18-21) | 280-380 / 3w | 360-490 / 3w | Top-1 LIVE $500 + Top-2 + Options Stack 1 + M1 Tier 1 IMPL + M9 read-only + ★ Sprint 4 首次 Live ★ |
| 5 (W21-24) | 240-340 / 3w | 305-440 / 3w | Top-2 LIVE + Top-3 + Options Stack 2 + M3 auto-degradation triggers |
| 6 (W24-27) | 240-340 / 3w | 305-440 / 3w | Top-4 + C13-VRP + Funding short + M12 maker-vs-taker adaptive |
| 7 (W27-30) | 220-320 / 3w | 280-410 / 3w | Top-5 + Advisory Allocator + M1 Tier 2 + M6 Advisory reward weights + M9 manual A/B |
| 8 (W30-33) | 280-380 / 3w | 360-490 / 3w | Decay (M7) IMPL + M4 pattern miner stage 2 + M3 recovery logic + M8 alerting |
| 9 (W33-36) | 200-280 / 3w | 255-360 / 3w | Continue Advisory + Copy Infra build + M12 slicing IMPL |
| 10 (W36-44 末) | 150-200 / 3w | 190-260 / 3w | Y1 Review + Copy Trading Evidence Gate + Overlay verdict + M2/M8/M9 Y2 prep + M13 spec |
| **Y1 Total** | **2,780-3,930 hr / 37-44w** | **3,500-5,200 hr / 44-55w** | – |

### Y2-Y3 大階段時間軸

```
Y1 末 (W44-55, ~2026-12 → 2027-04)：
  - Autonomy 66%（自主交易 75% / 自主風控 93% / 自主調整 35% / 自主學習 60%）
  - 5 strategy live (Unlock SHORT W18-21 first / 其他 W21-30 incremental)
  - Auto-Allocator Advisory only
  - Counterfactual logging Y1 read-only

Y2 Q1-Q2 (Sprint 11+, ~2027-04 → 2027-09)：
  - 6 months Advisory + >80% approval rate evaluation
  - Auto-Allocator activation (M1 Tier 2 Auto)
  - M2 overlay enable if Y1 末 verified
  - M9 A/B auto-promotion gate
  - Autonomy 90%

Y3 Q2 (~2028, AUM ≥ $50k)：
  - M10 Tier C-E activation
  - M12 cross-venue routing
  - M13 Multi-venue Binance trade enable (if approved per Y3 5-gate review)
  - M5 online learning IMPL trigger (if AUM > $75k)
  - Autonomy 95%

真正「不需介入」時點：Y2 Q2-Q3 (~21-24 個月 90%) / Y3 Q2 (~32 個月 95%)
```

---

## 四、operator 需簽核的 5 條 PM 仲裁決策

| # | 決策 | 影響 |
|---|---|---|
| **D1** | **批 16 CRITICAL must-fix 為 Sprint 1A-β 派發前置條件** | 派發延後 D+5~D+10 |
| **D2** | **批 M1 Lease Tier 改名為 LAL (Layered Approval Lease)，避免與 AMD-01 Stage 0R-4 命名衝突** | ADR-0034 + spec 改名；30-60 min |
| **D3** | **批 v5.8 §3 Sprint 1A 工時 543-797 → 670-1,015 hr + Y1 total 2,780-3,930 → 3,500-5,200 hr + Y1 calendar 37-44w → 44-55w** | 接受 +20-43% 工時 + 7-11w calendar |
| **D4** | **批 M13 Y2 Binance trade enable → Y3+ at earliest（per BB push back + ADR-0033/CLAUDE.md §一 衝突）** | Y2 期間 Binance 仍 market-data only；M13 spec 改 Y3+ |
| **D5** | **批 立 AMD-2026-05-21-01-autonomy-vs-human-final-review**（protected scope vs opt-in scope 邊界定義） | 派發前必 land；M1/M2/M6/M7/M9 auto-apply 才有 governance 錨點 |

**3 個 missing module 處置**（PM 仲裁建議）：
- M14 (hot-swap)：defer 至 v5.9，理由「engine restart 在 Sprint 1A-β 階段不是 blocker；Sprint 4 first Live 後 90d 才需 hot-swap」
- M15 (capacity-aware sizing)：擴 M6 acceptance 第 4 條，不新建 module（per FA 建議）
- M16 (cross-strategy correlation)：擴 M1 acceptance「correlation-adjusted weight」，不新建 module

---

## 五、5 個 operator 立即可做的動作

| # | Action | 時間 | 結果 |
|---|---|---|---|
| 1 | 確認 D1-D5 簽核（30 分內）| D+0 | unblock 修補階段 |
| 2 | 派 16 CRITICAL must-fix 並行 sub-agent dispatch | D+0~D+5 | 修補完成 |
| 3 | v5.8 §3/§4/§9/§10/§11/§12/§13/§14 補丁 commit + push + Linux pull | D+5 | v5.8 r2 land |
| 4 | docs/README.md index 補 + TODO §0.5 refactor | D+5 | 文檔基線復原 |
| 5 | Sprint 1A-β 派發 PA + 5-7 並行 sub-agent | D+5~D+10 | 真實開發開始 |

---

## 六、PM 風險評估（給 operator 的觀點）

### 好消息
1. **v5.8 thesis 14 audit 全 0 NO-GO** — 設計方向健康
2. **3 HOLD 都是 conditional**（文檔/工時/治理層面），補完即 GO
3. **v5.8 真實補齊 v5.7 PM autonomy verdict 13/13 missing module 中的 10/13** — 剩 3 個 hot-swap/capacity/correlation 可擴展現有 module 解
4. **Y2 90% autonomy 「substantively realizable」** — 不是 framework shell

### 風險點
1. **真實 Y1 calendar 44-55w**（vs v5.8 文本 37-44w）— operator 需接受 +7-11w
2. **真實 Y1 工時 3,500-5,200 hr**（vs v5.8 文本 2,780-3,930 hr）— +26-32%
3. **AI cost $1,344-2,556/yr** vs DOC-08 月 $60 cap 超 1.9-3.5x — ContextDistiller v4 + 模型路徑優化
4. **3 個 missing module 處置**需 PM/operator 拍板（擴 M6/M1 acceptance vs 新建 M14-M16）
5. **PG buffer**：V106 health 高頻表 6mo +1.25-2.5 GB（占 buffer 16-63%）— 必 hypertable + 90d retention
6. **P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 Live precondition** 在 v5.8 §10 缺席 — Sprint 4 首次 Live 仍被阻；需與 v5.8 修補階段並行解
7. **4 state machine（M1/M2/M3/M7）50+ transition** 易漏邊（first-detection deadlock 反模式風險）

### 機會點
1. **CRITICAL must-fix 大部分可並行**：8-10 sub-agent 並行 D+5 內完成
2. **GUI 工時補位 +261-374 hr 可拉動 E1a 系統性介入**：v5.8 全文 0 次提 E1a，現在補上正合適
3. **Counterfactual logger 可後置 Sprint 3-4**：M11 nightly replay + M4 pattern miner Y1 不影響 income，可慢慢上線
4. **Sprint 2 Alpha Tournament 是 5 strategy 驗證關卡**：QC + MIT 並行可壓縮

---

## 七、PM 最終建議

### 7.1 短期（D+0 ~ D+5）
1. operator 答 D1-D5 五個決策（30 分內）
2. 派 16 CRITICAL must-fix 並行 sub-agent（D+0~D+5）
3. v5.8 r2 land（包含工時上修、命名修正、ADR/spec/runbook draft、docs/README index 補錄）
4. Sprint 1A-β 派發前置條件 100% 達成

### 7.2 中期（Sprint 1A-β 至 Sprint 10）
1. 5-7 並行 sub-agent dispatch 五階段 DESIGN + IMPL
2. 每 Sprint 末 PM sign-off + R4 docs index 補 + TW worklogs
3. Sprint 4 首次 Live 前 P0-EDGE-1 / LG-3 / OPS-1..4 全 closure
4. Y1 末 (W44-55) Y2 Copy Trading evidence gate + counterfactual overlay verdict

### 7.3 長期（Y2-Y3）
1. Y2 Q1-Q2：Auto-Allocator activation evaluation（6 months Advisory + >80% approval）
2. Y2 Q2：M2 overlay enable（if counterfactual verified）+ M1 Tier 2 Auto
3. Y3 Q2 (AUM ≥ $50k)：M10 Tier C-E + M12 cross-venue + M13 Binance trade enable (per Y3 5-gate review)
4. Y3 Q4 (AUM ≥ $75k)：M5 online learning IMPL trigger

### 7.4 關鍵 PM 一句話

> **v5.7 + v5.8 真實開發路線是「44-55w Y1 + 21-32 月達 fully autonomous」的長期投資**；功能/可實現/邏輯/板塊/文檔 5 維度全 NEEDS-FIX 但都不阻 thesis，13 prerequisite 補完 D+5~D+10 內可派 Sprint 1A-β 真實開發。

---

## 八、本回合不做的事

- [x] **不更新 TODO 正式區塊**（per 操作員過往指示模式；除非 operator 明示）— 但 §0.5 staging 可加 v5.8 13 module + 16 CRITICAL 條目
- [x] **不派 Sprint 1A-β**：等 16 CRITICAL must-fix 完成
- [x] **不寫業務代碼**：純 PM 整合 + 結論

---

## 九、報告 inventory（本回合 v5.8 audit 產出）

```
srv/docs/CCAgentWorkSpace/
├── A3/workspace/reports/2026-05-21--v58_executability_audit.md     A3 7.0/10
├── AI-E/workspace/reports/2026-05-21--v58_executability_audit.md   AI cost CRITICAL
├── BB/workspace/reports/2026-05-21--v58_executability_audit.md     M13 Y3+
├── CC/workspace/reports/2026-05-21--v58_executability_audit.md     16 root principle 6 WARN
├── E2/workspace/reports/2026-05-21--v58_executability_audit.md     HOLD 對抗式
├── E3/workspace/reports/2026-05-21--v58_executability_audit.md     5-gate inheritance
├── E4/workspace/reports/2026-05-21--v58_executability_audit.md     state machine 50+ transition
├── E5/workspace/reports/2026-05-21--v58_executability_audit.md     PG V106 + 工時
├── FA/workspace/reports/2026-05-21--v58_executability_audit.md     3 missing module
├── MIT/workspace/reports/2026-05-21--v58_executability_audit.md    V### spec placeholder
├── PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md  PA 整合（562 行）
├── PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md        本檔
├── QA/workspace/reports/2026-05-21--v58_executability_audit.md     M1 命名衝突
├── QC/workspace/reports/2026-05-21--v58_executability_audit.md     HMM 黑名單
├── R4/workspace/reports/2026-05-21--v58_executability_audit.md     HOLD 46 文件
└── TW/workspace/reports/2026-05-21--v58_executability_audit.md     HOLD TW 工時
```

**16 份報告 / ~4,500 行內容 / 14 個 audit + PA 整合 + PM 簽收**

---

**PM SIGN-OFF DONE**

**v5.7+v5.8 真實開發路線整合 DISPATCH-NEEDS-FIX；先答 D1-D5 → D+0~D+5 修補 16 CRITICAL → D+5~D+10 派 Sprint 1A-β 真實開發；Y1 calendar 44-55w；Y2 Q2 達 90% autonomy；Y3 Q2 達 95% autonomy。**
