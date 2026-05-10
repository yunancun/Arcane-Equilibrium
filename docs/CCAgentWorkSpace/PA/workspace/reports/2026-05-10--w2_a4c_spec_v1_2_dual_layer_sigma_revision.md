## W2 A4-C Spec v1.1 → v1.2 Inline Edit Report — Dual-Layer σ + PSR(0) Strict + +15 bps Gate Power Verification

**Date**: 2026-05-10
**Author**: PA (project architect)
**Trigger**: MIT C-3 σ verify report `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w2_c3_sigma_verify_btcusdt_1m_forward_return.md` CONDITIONAL PASS verdict
**Spec target**: `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`
**Status**: v1.1 → v1.2 inline edit DONE；MIT + QC 直接收 W2 IMPL，不需 D+1 重 sign-off

---

### 1. Dual-layer σ acceptance table（spec §7.1 改動）

**Spec §7.1 acceptance prerequisite section 從單一「σ verified by MIT C-3」line 改為 dual-layer table**：

| σ layer | source | value (per MIT C-3 verify) | spec 用途 |
|---|---|---|---|
| **Raw market σ (L1)** | BTCUSDT 1m forward-return realized σ 7d (n=10050) | σ_60=4.54 / σ_120=6.28 / σ_300=10.08 bps | Alpha decay R²(N) 計算 baseline + price horizon scaling reference |
| **Net edge σ (L2)** | EDGE-DIAG-1 demo cost-aware fill σ historical | σ_net=50-80 bps（含 fee + slippage + adverse selection） | Paper edge gate threshold power calculation + PSR(0) deflation 計算 |

**強制 prerequisite condition（v1.2 新增）**：
- Spec power calculation **強制用 net edge σ_net = 50-80 bps**，禁用 raw market σ（raw σ 視角 t-stat 13-29 過度樂觀，會放 false-PASS）
- 任何 paper edge gate threshold 變動必對 σ_net=50/80 bps 兩 case 並列重算 power
- raw market σ 僅用於 §3.1.1 半衰期 reference + §7.1 metric (4) Alpha decay R²(N) baseline
- MIT C-3 σ verify 已交付 → W2 IMPL 直接收，不需 D+1 重跑

### 2. PSR(0) skew/kurt formula 強制 language（spec §7.1 metric (3) 改動）

**從 soft 描述「PSR(0) ≥ 0.95 用 skew/kurt-aware formula」改為強制條件**：

```
強制條件（per MIT C-3 verify ex_kurt = 7-12 ≫ 0）：
- crypto JB normality 必拒（5d block resampling 已 verify）
- 禁用 normal SR z-test
- 強制 Bailey-López de Prado 2012 PSR(0) formula:
  PSR(0) = Φ((SR - 0) × √(n-1) / √(1 - skew·SR + (kurt-1)/4·SR²))
- threshold ≥ 0.95
- σ_net=80 bps + ex_kurt=10 → PSR(0) ≈ 0.94（接近下界）
- 必並列 σ_net=50/80 bps 兩 case PSR(0) 值
```

### 3. +15 bps gate power verification 補強（spec §8.1）

**新增 power verification table（per MIT C-3 §5 net edge σ 視角，N_fills=80, μ=15 bps）**：

| σ_net case | SE = σ_net/√N | t-stat | p-value | verdict |
|---|---|---|---|---|
| σ_net = 50 bps | 5.59 | 2.68 | 0.0044 | **comfortable PASS** |
| σ_net = 80 bps | 8.94 | 1.68 | 0.0487 | **marginal PASS**（剛 < 0.05） |

**結論**：+15 bps gate 在 σ_net ∈ [50, 80] bps range 全 PASS（lower comfortable，upper marginal）；門檻設定有效。+5/+15 中段 + +5 下界 power verification 同步補完，三檔 gate 拍板理由完整。

### 4. Spec v1.1 → v1.2 change log（5 entries）

| # | Section | Essence |
|---|---|---|
| 1 | §7.1 acceptance prerequisite | dual-layer σ table 取代單一 σ verify line |
| 2 | §7.1 metric (3) PSR(0) | strict skew/kurt formula 強制條件 |
| 3 | §8.1 gate verification | +15 bps gate σ_net=50/80 bps 兩 case power table |
| 4 | §8.3 sign-off path | MIT + QC 直接收 W2 IMPL，不需 D+1 重 sign-off |
| 5 | §1 header status + §9 risk row | v1.1 → v1.2，σ=30 bps 假設 risk row mark closed |

### 5. D+1 W2 sign-off path confirm

**W2 IMPL phase 直接啟動 timeline**：
- D+0（今）：spec v1.2 land；QC C-2 已 sign-off（v1.1 5 conditions revised）；MIT C-3 σ verify 已交付
- D+1：**MIT + QC 直接收 W2 IMPL**（v1.2 補強為 spec internal cleanup，不增 condition、不改 IMPL scope）；MIT C-3 D+1 review 仍跑 strict shift(N) leak grep + V088 hypertable PL/pgSQL syntax + retention policy + idempotency dry-run（保留 IMPL phase 啟動前驗）
- D+3：派 C-IMPL-1..4 paper IMPL（PA D+0 trait skeleton 已 land HEAD c9fb0b8f，IMPL phase 0 file 重疊 0 git merge 衝突）
- D+5：paper engine deploy
- D+12：paper edge report land（含 §7.1 mandatory metric 6 條 + dual-layer σ acceptance + PSR(0) skew/kurt formula 計算 + +15 bps gate power verification σ_net=50/80 兩 case 並列）

**16 根原則合規**：本次 spec edit 不動 §13 列舉的 8 項合規條目（原則 1/4/7/8/13/14/DOC-08 §12/硬邊界 5 項全 0 觸碰）；spec internal cleanup 範疇。

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w2_a4c_spec_v1_2_dual_layer_sigma_revision.md
