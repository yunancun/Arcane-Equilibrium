# v5.8 13-Module Autonomy Expansion 執行性審核 — FA 視角

**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.8 13 module 涵蓋 PM verdict 10/13（M3 hot-swap、M6 capacity-aware、M7 cross-strat correlation 三項 PARTIAL/MISSING），acceptance criteria 大致清晰但 M1/M3/M11/M12 量化 threshold 仍欠補，5-gate 與 §11 mitigation 需在 Sprint 1A 前完成 4 項 must-fix。

## 0. 13 module vs PM autonomy verdict 13 missing module 對照

| PM verdict # | 訴求 | v5.8 對應 | 判定 | 缺口 |
|---|---|---|---|---|
| M1 | Auto-Allocator 本體（Discovery 結果自動配置 capital + 啟用 schedule） | v5.8 M1 + M10 | **PARTIAL** | Tier 1-4 自動執行框架已定，但 "Discovery → 自動 capital 分配" 端到端工作流 acceptance 缺 |
| M2 | Overlay enable mechanism | v5.8 M2 | **MATCHED** | acceptance 5 state transitions 清楚 |
| M3 | Strategy hot-swap（不重啟 engine） | v5.8 **無對應**（M7 是 decay 非 hot-swap，M3 是 risk health） | **MISSING** | 應補 M14 或 M7 擴 scope |
| M4 | Self-supervised parameter discovery | v5.8 M4 | **MATCHED** | DRAFT writeback workflow 完整 |
| M5 | Online learning | v5.8 M5 | **MATCHED** | Y3+ activation criteria 3 條清楚 |
| M6 | Capacity-aware sizing（流動性/depth 感知） | v5.8 **無直接對應**（M6 是 Bayesian opt 參數，M12 routing 涉 slippage 但非 sizing） | **MISSING** | 應補 M6 acceptance 第 4 條 "depth/liquidity bounds"，或新建 module |
| M7 | Cross-strategy correlation 動態 sizing | v5.8 **無對應** | **MISSING** | PM verdict M7 "多策略同向同 symbol 自動 down-weight"；v5.8 M1+M6 未列 |
| M8 | Anomaly runtime | v5.8 M8 | **MATCHED** | severity taxonomy + Y1/Y2 response 區分 OK |
| M9 | A/B framework | v5.8 M9 | **MATCHED** | 4 test types 完整 |
| M10 | Discovery 全自動 | v5.8 M4 + M10 | **PARTIAL** | M10 Tier capital trigger 清楚；但 "Discovery → Auto-Allocator → 配置" 全自動 acceptance 不全 |
| M11 | Self-healing | v5.8 M3 + M11 | **PARTIAL** | "divergence threshold + auto-rollback" 量化 criteria 待補 |
| M12 | Adaptive order routing | v5.8 M12 | **MATCHED**（IMPL 延 Sprint 6+） | OK |
| M13 | Multi-asset | v5.8 M13 | **MATCHED** | OK |

**統計**：MATCHED 7/13、PARTIAL 3/13、MISSING 3/13。**3 個 MISSING 是 v5.8 重大業務遺漏，須在 §11 或 §1 補解釋為何 defer 或新建 M14/M15/M16**。

## 0.5 4 維度 autonomy 覆蓋

| 維度 | v5.8 module | 覆蓋判定 | gap |
|---|---|---|---|
| 自主交易 | M1+M12+M13 | **OK** | M12 IMPL 延 Sprint 6+；可接受 |
| 自主風控 | M3+M8+M11+M2 | **OK 但有交叉** | M3/M8 邊界需釐清（重疊區），acceptance §3 應加 "M3 與 M8 trigger 互斥規則" |
| 自主調整 | M6+M7+M9+M10 | **PARTIAL** | 缺 **cross-strategy correlation re-sizing**（PM M7）+ **capacity-aware sizing**（PM M6） |
| 自主學習 | M4+M5+M10+M11 | **OK** | M5 online learning 與 M4 DRAFT 串接點需 acceptance 補 |

**結論**：自主交易/風控/學習達 operator 4 維度；**自主調整缺 2 子能力**（correlation / capacity）→ must-fix #1

## 0.6 13 module 業務 acceptance criteria 清晰度

| Module | Acceptance | 判定 | 缺口 |
|---|---|---|---|
| M1 | Tier 2 5 條 + Tier 3/4 operator approve | **PARTIAL** | Tier 2 量化 threshold（sharpe ≥ X / 樣本量 / max_dd）具體值未定 |
| M2 | 5 transitions | **CLEAR** | — |
| M3 | 5 domain × threshold | **PARTIAL** | 各 domain 具體 threshold 數值待補 |
| M4 | DRAFT writeback | **CLEAR** | — |
| M5 | Y3+ activation | **CLEAR** | — |
| M6 | input/output + bounds + 30% rollback | **CLEAR** | — |
| M7 | 5 state transitions | **CLEAR** | — |
| M8 | severity taxonomy + Y1/Y2 response | **CLEAR** | — |
| M9 | 4 test types + 統計 methodology | **CLEAR** | — |
| M10 | Tier A-E trigger + 啟用 criteria | **CLEAR** | — |
| M11 | nightly divergence threshold | **PARTIAL** | divergence threshold 數字待確認 |
| M12 | dimensions + bounds | **CLEAR** | — |
| M13 | AssetClass + Venue enum + Y2 workflow | **CLEAR** | — |

**統計**：CLEAR 9/13、PARTIAL 4/13、MISSING 0/13。**M1/M3/M11 三個 PARTIAL 量化 threshold 為 must-fix #2**

## 1. Top 3 執行性風險

### Risk 1：3 個 PM verdict missing module 未在 v5.8 §11 標"defer/補module"
- 嚴重度：HIGH
- 證據：PM verdict M3 hot-swap / M6 capacity-aware / M7 cross-strategy correlation 三項 v5.8 無對應
- 影響：v5.8 名為「13 module expansion」但實際 PM verdict cover 10/13；§13 邏輯成立但需 §11 明示 defer 至 v5.9 或新增 M14

### Risk 2：5-gate 業務適用範圍未在 §11 明示
- 嚴重度：MED
- 證據：13 module Y2/Y3 啟用是否每次都過 5-gate（Discovery → Audit → Validate → Operator Sign-off → Stage Promote），未明示
- 影響：M5 online learning 與 M11 replay Y3+ 啟用時若繞 5-gate，違 16 根原則第 3 條

### Risk 3：M3 / M8 / M11 風控三 module trigger 邊界 overlap
- 嚴重度：MED
- 證據：M3 risk health degradation + M8 anomaly + M11 nightly divergence 三者在 PnL drawdown / strategy abnormal 場景同時 trigger，acceptance 未定 mutual exclusion
- 影響：runtime 重複 disable + 重複 rollback；E1 IMPL 沒有「哪個 module owns 哪個 trigger」明確 contract

## 2. v5.8 業務遺漏板塊（PM verdict 提了但 v5.8 沒覆蓋）

| # | PM verdict 訴求 | v5.8 遺漏點 | 建議 |
|---|---|---|---|
| 1 | M3 Strategy hot-swap（不重啟 engine） | 13 module 全無 | 新增 M14 "Engine hot-swap registry"；defer Sprint 4+ 但 v5.8 必列 |
| 2 | M6 Capacity-aware sizing | M1 + M6 都未提 | 擴 M6 acceptance 第 4 條 "orderbook depth bounds"，或新增 M15 |
| 3 | M7 Cross-strategy correlation re-sizing | M1/M6/M7 三 sizing module 都未提 correlation matrix | 擴 M1 acceptance "correlation-adjusted weight"，或新增 M16 |

## 3. 5 策略 × Stage gate × 13 module hook 矩陣

| 策略 | Y1 Stage | 已串 module | 未串 module |
|---|---|---|---|
| C10 (grid 主力) | Stage 4 | M2/M3/M8/M11 | M1/M6/M7/M10 |
| Unlock | Stage 2 (1R) | M2/M4/M8 | M1/M6/M7 |
| Pairs | Stage 1 (R0) | M4/M10 candidate | 其他全部 |
| C13 | Stage 0 (DRAFT) | M4 DRAFT | 其他全部 |
| Funding short | Stage 0 (DRAFT) | M4 DRAFT | 其他全部 |

**結論**：C10 是 v5.8 主要驗證 surface；C13/Funding short Y1 只串 M4，§1 §13 應明示 "Y1 13/13 覆蓋率 30%"；Sprint 1A-β-ε must-deploy = M2/M3/M8/M11

## 4. operator forgetfulness mitigation 業務鏈 (§11) 完整度

| Failure | mitigation | 完整度 |
|---|---|---|
| F1 忘記啟用 module | weekly report | OK |
| F2 忘記 review replay divergence | M11 auto-rollback + 周報 | **PARTIAL** — auto-rollback threshold 未定 |
| F3 忘記 update strategy config | M4 DRAFT | OK |
| F4 忘記 Tier 3/4 approve | M1 escalate | OK |
| F5 忘記 monitor anomaly | M8 escalate | OK |
| F6 忘記 staged rollout | M2 stage 強制 | OK |

**完整度**：5/6 OK + 1/6 PARTIAL → must-fix #3
**遺漏**：F7 忘記響應 M3 health critical / F8 忘記 review A/B test 結果

## 5. 對 PA+PM 匯總必收 top 3

1. **3 個 PM verdict missing module（M3 hot-swap / M6 capacity / M7 correlation）必須在 v5.8 §11 或 §13 明示處置**（defer + ETA 或新增 M14-M16）
2. **M1 / M3 / M11 量化 threshold 補齊**（Tier 2 sharpe 值、5 health domain threshold 數字、replay divergence bps 閾值）
3. **5-gate 在 13 module Y2/Y3 啟用時的適用範圍**必須在 §11 明示

## 6. v5.8 派發前 must-fix（4 條）

1. **§13 補 "M3 hot-swap / M6 capacity-aware / M7 correlation 處置決定"**（defer 至 v5.9 + 原因 / 或補 M14-M16）
2. **M1 / M3 / M11 量化 threshold**：
   - M1 Tier 2 自動執行 5 條的「sharpe / sample / max_dd / live_time_min」具體值
   - M3 5 health domain 各自 threshold（PnL drawdown N%、latency N ms、fill rate N%、error rate N%、capital util N%）
   - M11 nightly replay divergence threshold（"P&L 差距 ≥ X bps"）
3. **§11 補 F2 mitigation 完整量化 + 新增 F7（health critical 響應）+ F8（A/B test 響應）**
4. **§3 加 "M3 / M8 / M11 trigger mutual exclusion contract"**

## 7. Sprint 1A-β-ε 期間 should-fix

1. C10 串接 M2/M3/M8/M11 的 E1 acceptance 必 Sprint 1A-β 開工前定稿
2. Unlock 串接 M2/M4/M8 acceptance（Sprint 2A 開工前）
3. §1 Sprint 4-7 補 "Discovery → Auto-Allocator 端到端" 工作流圖
4. §3 acceptance 加 "M3 與 M8 邊界 ownership 表"
5. §9 5-gate 應用範圍 — 13 module 各自 Y2/Y3 啟用是否每次都過 5-gate，明示
6. AMD-2026-05-15-01 對齊：M1 Tier 3/4 永遠 operator approve ✓；M7 auto-demote 在 acceptance 第 6 條明示 "demote fail-closed default"
7. §13 補 "v5.8 業務 acceptance 與 16 根原則第 5 條（生存>利潤）對齊聲明"

## 補充：5 策略 × 5-gate 適用範圍速查

| 階段 | C10 | Unlock | Pairs | C13 | Funding short |
|---|---|---|---|---|---|
| Discovery | passed | passed | passed | in-progress | in-progress |
| Audit | passed | passed | dormant | not-yet | not-yet |
| Validate | passed | shadow | not-yet | not-yet | not-yet |
| Operator Sign-off | YES (Y1) | YES (1R) | not-yet | not-yet | not-yet |
| Stage Promote | Stage 4 | Stage 2 (1R) | Stage 1 (R0) | Stage 0 | Stage 0 |

## 16 根原則對齊驗證

| 原則 | v5.8 module 對齊 | 判定 |
|---|---|---|
| #3 AI→Lease→複核→執行 | M1 Tier 3/4 / M2 / M11 都有 operator gate | ✅ |
| #5 生存>利潤 | M6 30% rollback / M7 decay disable / M9 stop-loss test | ✅ |
| #7 學習≠改寫 Live | M4 DRAFT writeback / M5 Y3+ 才啟用 | ✅ |
| #11 P0/P1 內最大自主 | M1 Tier 1-2 邊界內 + Tier 3/4 escalate | ✅ |

**結論**：16 根原則 4/4 alignment OK；唯 PARTIAL module 量化 threshold 補齊後即可派發

## 最終 Verdict

**GO-WITH-CONDITIONS**：v5.8 13 module 整體業務設計與 PM autonomy verdict alignment 達 10/13；3 個 missing module（hot-swap / capacity / correlation）+ 4 must-fix（§13 處置 / M1-M3-M11 量化 / §11 F2/F7/F8 / §3 trigger mutual exclusion）完成後可派發 Sprint 1A
