# QC Short Re-Review — phys_lock Live Enable AMD DRAFT

**Reviewer**: QC (Quantitative Consultant)
**Date**: 2026-05-16
**Subject**: `2026-05-XX-XX-phys-lock-live-enable-draft.md` v0.1 DRAFT
**Mode**: Short focused re-review — verify AMD framing 對齊 QC round-2 §6 + counterfactual gate 數學嚴格性 + one-flag-per-phase 立場一致 + rollback 健全性
**Verdict**: **APPROVED-CONDITIONAL** (2 must-fix + 3 should-fix + 2 nice-to-have)

> 註：QC agent read-only；本檔由主會話按 QC agent 返回原文存檔。

---

## §1 Framing 嚴謹性 (transaction cost economics)

**判定**: PASS with minor clarification needed.

AMD §1 末段「phys_lock = profit-protection (α_holding truncation policy)，非 risk-bypass 也非新 alpha source」**在 transaction cost economics 嚴格定義下分類正確**。我復算分解：

```
NetPnL = α_entry + α_holding + α_exit − (fee + slippage + impact + funding)
α_holding = ∫[t_entry, t_exit] dP_favourable(s) ds
phys_lock 干預 = truncate t_exit at peak ATR giveback condition
              = policy on α_holding upper bound + tail-loss truncation
```

phys_lock **不**改變 informational alpha（α_entry/α_exit）；只在 holding window 內以 path-dependent rule 截斷 α_holding 上下尾。這是 **policy on holding distribution 的二階矩 / max-DD truncation**，數學上**屬 cost-side optimization（risk-adjusted return improvement via variance/skew reduction），非 alpha extraction**。

**與 AMD-2026-05-15-02 §1 對比一致性**: AMD-2026-05-15-02 §1 定義 close-maker-first = 「alpha-impact-adjacent execution-quality pathway」 — 兩者語義一致（都是 cost/quality 範疇，非新 α），本 AMD framing 嚴格度甚至**更高**（明文標 α_holding truncation policy 分類，比 AMD-2026-05-15-02 「alpha-impact-adjacent」更精確）。✅

**Minor clarification needed (SHOULD)**: §1 framing 應補一行「phys_lock 對 Sharpe 改善的數學機制 = E[NetPnL] 略降 + Var(NetPnL) 顯著降 + tail-loss truncation → Sharpe 上升條件為 σ_reduction × Sharpe_baseline > μ_reduction」。當前 framing 對方向 sound 但 magnitude 條件未明文。

---

## §2 Counterfactual 4-criterion 嚴格性

**判定**: PARTIAL — 3 條 sound，1 條過嚴需修正。

§5.2 PASS criteria 逐項復算：

**(a) median(A − B) < −2 bps**: ✅ 合理。−2 bps 是 fee saving range 中性下界（per AMD-2026-05-15-02 §1.2 footnote 0.5-2.0 bps net）的對偶 threshold；要求 with-lock 顯著優於 without-lock 至少 2 bps。**對齊 conservative 下界**。

**(b) 95% one-sided CI 上限 < 0**: ✅ 數學上 sound。one-sided test 適合 directional hypothesis（H1: with-lock better）；95% CI 對應 α=0.05。

**(c) Sensitivity sweep**: ⚠️ **過寬鬆，需收緊**。`min_hold_secs ± 50% / giveback_floor ± 0.1 / peak_atr_norm ± 0.2` 是 3 維獨立 sweep，但 demo n=86 fires 切到 3×3×3 = 27 sub-cells 後 per-cell n ≈ 3，**統計顯著性歸零**。應改為「3 個 param 各自獨立 sweep（one-at-a-time），不做 full Cartesian；每個 param 在 ± 範圍兩端 2 點驗 median(A−B) 仍 < 0」— 共 6 sub-test，每個 n=86 維持 power。

**(d) Per-symbol ≥ 70% directional positive**: ❌ **過嚴 + 數學依據薄弱**。86 fires / 25 symbols ≈ 3.44 fires/symbol 平均，但實際分布**極不均**。要求 70% per-symbol direction = 35/49 symbols（若 ≥5 fires 估約 7-10 symbols qualified）必須 7-8 個 PASS — 過於 cherry-pick-resistant 但 power 不足。**應改**：(i) 只對 fires ≥ 10 symbols 做 per-symbol t-test；(ii) directional threshold 改 60%（Wilson-CI lower bound ≥ 50% 對應），non-significant cells 視 NEUTRAL；(iii) ≥10 fires symbols 數量 < 5 時跳過此 criterion，僅依賴 (a)(b)(c)。

**Wilson-CI 嚴謹性 (n=86)**: ✅ 適合。Wilson interval for proportion 在 n=86 下對 small-event-rate 比 Wald 穩健 50-100x；mirror AMD-2026-05-15-02 AC-14/AC-18 precedent。

**Block-bootstrap**: §5.1.3 明文 `block-bootstrap 防 path autocorrelation`，n_bootstrap=1000，✅ crypto returns 已知 autocorrelation 結構，block bootstrap 正確選擇。block size 應補明（建議 √n ≈ 9 or AR(1) coefficient 1/(1−ρ) 估）。

---

## §3 One-flag-per-phase 數學論證對齊

**判定**: ALIGNED with QC round-2 §6 + AMD-2026-05-15-02 §4 DEFER 立場。

QC round-2 §6.1 結論「SUPPORT FA DEFER + 加額外條件：phys_lock 啟用前必先跑 counterfactual analysis on demo 86 fires」**已被 AMD draft Gate 3.2 完整 mirror**。

數學論證鏈條對齊：
1. **P0-EDGE-1 alpha-deficient regime → phys_lock 鎖 noise 而非 alpha 風險** ✅ AMD §4.2 明文 + 引 QC §6 反問
2. **One-flag-per-phase 違反成本 = observability noise 在 close-maker-first Phase 2b 段不可分離** ✅ AMD §4.1 緩解 1 明文「Gate 3.1 強制本 AMD enable timing 必在 Phase 2b PASS 之後」
3. **Demo-loose-live-strict 政策不是 prohibitive 是 negotiable** ✅ AMD §4.3 明文判定「政策上是 negotiable，需 operator carve-out + counterfactual evidence 雙重門控」

**對齊度 100%**；但 AMD §4.2 引述 QC §6 反問後，**緩解措施只強制 Gate 3.2 counterfactual 在 demo regime，未強制 live regime 二次驗證**。

**MUST-FIX-1**: AMD §4.2 殘留風險 HIGH 條 + §5 Counterfactual evidence packet 應補一個 Phase 2.5（命名建議 **Phase 2c LiveDemo Counterfactual Verification**）：enable 後**先 7d Live Demo observation period**，在此期間每筆 phys_lock fire 即時跑 counterfactual replay against same-instant live order book snapshot，**累積 ≥30 fires after live enable 再判定 net positive**。當前 §6.2 monitoring trigger「demo baseline 7d 偏離 2σ」是事後檢測，**不是 pre-commit gate**；rollback 雖然 1 tick 內可回，但 14d observation 期間累積虧損可能已物質。

---

## §4 6-gate Pre-enable Conditions 完整度

**判定**: 5/6 合理 + 1 條應補 + 1 條應升 hard gate。

| Gate | QC 判定 |
|---|---|
| 3.1 Phase 2b LiveDemo PASS | ✅ 必要 — observability 隔離前提 |
| 3.2 QC Counterfactual Analysis | ✅ 必要 — alpha-deficient regime 防禦核心 |
| 3.3 Operator 顯式 Sign-off | ✅ 必要 — demo-loose-live-strict policy 履行 |
| 3.4 P0-EDGE-1 狀態評估 | ⚠️ **應升 hard sub-criterion** — 現「不要求 closed」過寬鬆 |
| 3.5 AMD-2026-05-15-02 v0.5 patch | ✅ 必要 — governance trail hygiene |
| 3.6 AMD slot 編號 | ✅ 必要 — register completeness |

**MUST-FIX-2 (P0-EDGE-1 sub-criterion)**: §3 Gate 3.4 寫「不要求 P0-EDGE-1 closed」**過寬鬆**。應補 sub-clause：「**P0-EDGE-1 active 狀態下，要求 demo 14d rolling realized edge 不再惡化（[40] 不再變更負）+ AlphaSurface C1 或 W-AUDIT-8b funding skew 至少有 1 候選 alpha 通過 Stage 0R replay preflight 為 `eligible_for_demo_canary=true`**」。Gate 應排除「alpha pipeline 完全空 + EDGE-1 永久 active」極端 case。

**SHOULD-FIX-1**: §3 應補 **Gate 3.7 Mac/Linux 行為對稱驗證** — ExitConfig ArcSwap hot-reload + RuntimeRiskConfig 路徑必跑 Linux runtime live empirical 驗 1 tick visibility — Mac unit test PASS 不足。

---

## §5 Mathematical Consistency (DRAFT vs round-2 §6)

**判定**: 90% match + 2 處可補強。

**Match 點**:
- AMD §1 framing「α_holding truncation policy」精確對應 QC round-2 §6.1 Sharpe trade-off 表 ✅
- AMD §4.2 引 QC §6 反問原文「噪音 vs 真 alpha」+ 鎖利 ≈ stop-loss-on-favourable-noise 比喻 ✅
- AMD §5.1.3 paired bootstrap CI 95% (n=1000, block-bootstrap) **完整 mirror** QC round-2 §6 nice-to-have item 11 ✅
- AMD §5.2 FAIL conditions「median(A-B) ≥ 0 OR CI 跨 0」對應 QC round-2 §6 結論 ✅

**未完整匹配 (SHOULD-FIX-2)**:
- QC round-2 §6 暗示「alpha-deficient 下 phys_lock 鎖 noise 而非 alpha」是**結構性問題**，counterfactual 只能驗 demo 樣本期該結構是否成立，**不能保證 future regime shift 後仍成立**。AMD §5 evidence packet 應補一條 **5.1.6 Regime stability check**：取 demo 86 fires 按時序 split 前 43 / 後 43，分別計算 median(A−B)，若兩個 sub-period directional 不一致 → 樣本期 regime mix 不穩，counterfactual 結論 fragile。

**未完整匹配 (NTH-1)**:
- QC round-2 §6 nice-to-have item 10 「Funding settlement proximity hook」**未在本 AMD 體現**。Phase 2b LiveDemo PASS + phys_lock enable 後若 funding skew alpha (W-AUDIT-8b) 同期上線，funding settlement 前 30s phys_lock fire + maker close pending → 跨 settlement instant 風險。**NTH**: AMD §4 應補 risk item 4.6「Future funding alpha 交互」hook。

---

## §6 Rollback Path 健全性

**判定**: PASS with verification needed.

**ArcSwap hot-reload 1 tick visibility 數學保證**: ✅ 結構級保證成立。ArcSwap 設計即 lock-free read + atomic swap，`config.load()` 每次取 snapshot，下一筆 `compute_physical_decision()` invocation 必取 new value。**read-modify-write race 不存在**。

**三場景驗證**:
- 場景 A: `compute_physical_decision()` 已進入 Gate 1 但尚未到 Gate 4 → snapshot 在 Gate 1 取，整個函數調用內一致 ✅
- 場景 B: phys_lock fire 已決策 + OrderDispatchRequest 已送 IPC 但 close fill 尚未回 → **rollback 不影響此筆 in-flight**，pending fill 走原 path 完成 ✅
- 場景 C: phys_lock fire 已決策但 close maker order pending 30s 內 → rollback 觸發後 maker timeout → fallback to market（既有 path）✅

**SHOULD-FIX-3**: §6.1 verification 「rollback 後 1h `phys_lock_fires=true` 計數應為 0」過嚴，因為 1h 內可能還有 in-flight rollback 前已 fire 的 row。應改「rollback timestamp 後 fire_ts 累積應為 0」，不是「1h 內 phys_lock_fires=true 計數」。

**NTH-2**: §6.2 trigger 條件「`phys_lock_live_fire_rate` 與 demo baseline 7d 偏離 > 2σ」**2σ 太寬鬆**。crypto regime 波動 + small-n，daily fire rate Poisson(12)，σ ≈ 3.5，2σ ≈ 5 fires，day-to-day noise 容易誤觸。應改 **rolling 7d 偏離 vs demo baseline 7d**，避日級 noise。

---

## §7 QC Verdict

### **APPROVED-CONDITIONAL** (2 must-fix + 3 should-fix + 2 nice-to-have)

**Round-2 §6 + short re-review §2.3 + §5.2 + §6.1 數學論證對齊度 90%+**；framing 嚴謹；one-flag-per-phase + demo-loose-live-strict policy 履行完整；rollback ArcSwap 數學保證 sound；6-gate pre-enable conditions 大致完整。**但** 4-criterion counterfactual PASS 第 (c) sensitivity sweep 過寬鬆 + (d) per-symbol 70% 過嚴，需修正；Gate 3.4 P0-EDGE-1 sub-criterion 過寬鬆；regime stability check 缺失。

### Must-fix (blocking AMD land)

1. **§5.2 PASS criteria (c)(d) 修正**:
   - (c) `min_hold_secs ± 50% / giveback_floor ± 0.1 / peak_atr_norm ± 0.2` 改為 **one-at-a-time sweep**（共 6 sub-test，禁 full Cartesian 3×3×3）保 power
   - (d) per-symbol 70% 改為「**fires ≥ 10 symbols only + Wilson-CI lower bound ≥ 50% as directional positive threshold + ≥10-fires symbols < 5 時跳過此 criterion**」

2. **§3 Gate 3.4 P0-EDGE-1 sub-criterion 升 hard**:
   - 補「**demo 14d rolling [40] 不再惡化** + **AlphaSurface C1 或 W-AUDIT-8b funding skew 至少 1 候選 Stage 0R `eligible_for_demo_canary=true`**」雙條件

### Should-fix (pre-enable)

3. **§3 補 Gate 3.7 Linux empirical verification**
4. **§5 補 5.1.6 Regime stability check**:demo 86 fires split 前 43 / 後 43，driver median(A−B) directional consistency
5. **§6.1 rollback verification timestamp fix**: 改「rollback timestamp 後 fire_ts 累積應為 0」

### Nice-to-have

6. **§4 補 risk item 4.6**: Future funding alpha (W-AUDIT-8b) 上線後 phys_lock + funding settlement proximity 交互 hook
7. **§6.2 trigger threshold**: 2σ daily 改 rolling 7d 偏離 vs demo baseline 7d，避日級 noise 誤觸

**Confidence**: HIGH（基於 transaction cost economics framework + QC round-2 §6 數學論證 baseline + ArcSwap structural guarantee + Wilson-CI + block bootstrap small-n best practice）。
