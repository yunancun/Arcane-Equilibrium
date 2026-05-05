# QC Advisory — REF-20 R6 Calibration Label Spec

**Date**: 2026-05-05
**Author**: QC (Quantitative Consultant)
**Sprint context**: REF-20 Sprint C1 (R6 Fee/Execution Calibration), pre-DAG advisory
**Scope**: 純數學 spec，0 code 改動，0 commit
**Hard boundary**: 黑名單 (HMM / GARCH / VPIN / vol mean-rev / Donchian look-ahead) 不觸碰
**Persistence**: PM 持久化（QC role read-only，無 Write tool；本 spec 由 QC final assistant message 整段落檔）

---

## §0. 黑名單檢查

本 spec 不引用 HMM / GARCH / VPIN / vol mean-rev / Donchian look-ahead 任一方法。Regime detection (§5) 我**主動 DEFER 至 Sprint D**（理由詳該節），避開 HMM 誘惑；CI 計算 (§3) 用非參 percentile bootstrap 不用 GARCH；信賴度 (§2) 用 sample std + IQR 雙路而非任何時序模型。

## §1. 三 Label 切點數學定義（Rust IMPL boolean expression）

`execution_confidence ∈ {'none', 'limited', 'calibrated'}`，按 4 維度先後檢查（短路求值）：

```rust
// 為 each (symbol, strategy) cell 計算
fn derive_label(fills: &[FillRecord], now: Timestamp) -> ExecutionConfidence {
    // 維度 1: 樣本量
    let n = fills.len();
    if n == 0 { return ExecutionConfidence::None; }            // §6 trivial

    // 維度 2: freshness（最近 fill）
    let last_fill_age_days = (now - fills.last().unwrap().filled_at).as_days();
    if last_fill_age_days > 14.0 { return ExecutionConfidence::None; }   // 全 stale → none

    // 維度 3: fee_bps 統計量
    let fee_bps_vec: Vec<f64> = fills.iter().map(|f| f.fee_rate * 10000.0).collect();
    let fee_bps_mad = median_absolute_deviation(&fee_bps_vec);  // robust scale
    let fee_bps_iqr = iqr(&fee_bps_vec);                        // tail-robust width

    // 維度 4: 切點（按嚴格 → 寬鬆）
    let calibrated_ok =
        n >= 200
        && last_fill_age_days <= 7.0
        && fee_bps_mad < 3.0       // MAD-based σ < 3 bps（≈ normal σ < 4.45 bps）
        && fee_bps_iqr < 8.0;      // IQR < 8 bps（middle 50% width）

    let limited_ok =
        n >= 30
        && last_fill_age_days <= 14.0
        && fee_bps_mad < 8.0       // MAD < 8 bps（≈ normal σ < 12 bps）
        && fee_bps_iqr < 20.0;

    if calibrated_ok { ExecutionConfidence::Calibrated }
    else if limited_ok { ExecutionConfidence::Limited }
    else { ExecutionConfidence::None }
}
```

### §1.1 Reproducibility check 對 §1E 真實樣本

| Strategy | 7d combined fills | 預期 label | spec 通過？ |
|---|---:|---|---|
| grid_trading | 1162 | calibrated | n ≥ 200 ✓；fee_bps 因 PostOnly maker fill rate 36.6%（CLAUDE.md §三 [33]）不純 → MAD 視 demo 真實 fee_rate 分布；本 spec assumes MAD < 3 bps 達標（IMPL 端要驗，若 MAD ≥ 3 → 降 'limited'，spec 容許）|
| ma_crossover | 635 | limited 或 calibrated boundary | n ≥ 200 ✓；切點交給 MAD/IQR 數據決定，不硬塞 'calibrated' |
| funding_arb | 99 | none **強制**降 | n=99 < 200 → fail calibrated；n=99 > 30 ✓ → limited 候選；**但**最後 fill 距今多久？若 V2 棄策略後 demo active=true 但已 1+ 週無 fire → fail freshness 14d → none |
| bb_breakout | 34 (14d) | none | n=34 > 30 但勉強；若 fee_bps σ 不穩或 freshness > 14d → none；spec 容許 |
| bb_reversion | 7 | none | n < 30 → none |

**結論**：spec reproducibly yields {grid='calibrated', ma='limited' or 'calibrated' boundary, others='none'} 對齊 PA §1E 預期。實際數值落點由 IMPL 階段 SQL fixture 在 Wave 1 驗。

### §1.2 為何 n=200 / 30 切點

- **n ≥ 30**：t-distribution 收斂 normal 的常規門檻（CLT minimum），低於此 sample mean 推論不可信
- **n ≥ 200**：QC memory 2026-04-02 lesson「200+ 筆同 regime 才能做參數優化，Deflated Sharpe 修正後觀察 SR 要扣 ~0.9」— 此處不是估 SR 是估 fee_bps mean+spread，但同樣需 power
- **不選 n=100**：30/200 拉開 calibrated 與 limited 區隔感；100 居中模糊
- **不分 regime**：見 §5

## §2. fee_bps Distribution Shape & σ 計算法

### §2.1 假設與真實形態判定

**先驗假設**：fee_bps 在單一 (strategy, symbol) cell 內 **bimodal mixture**：
- Mode A: maker fills（fee_rate ≈ 0.0002 = 2 bps）
- Mode B: taker fills（fee_rate ≈ 0.00055 = 5.5 bps）
- mixing weight = maker_fill_rate ∈ [0%, 100%]（CLAUDE.md §三 [33] 顯示 36.6%）

**這不是 normal**，也不是純 log-normal。是離散兩個 spike + 環境 noise（VIP tier 切換 / Bybit fee schedule 動態）。

### §2.2 σ 計算法選擇

| 方法 | 對 bimodal 反應 | 對 outlier 反應 | 推薦？ |
|---|---|---|---|
| Sample std (Bessel) | 兩 mode 距離拉大 → 高估 | 單 outlier 倍化 | ❌ |
| **MAD (Median Absolute Deviation)** | **median 落兩 mode 之間 → MAD 反映 mode-spread 真實感** | breakdown point 50% | ✅ 主選 |
| **IQR (Interquartile Range)** | Q1/Q3 落兩 mode 各自 → IQR ≈ mode 距離 | tail-robust | ✅ 副驗 |
| Bootstrap CI on mean | 樣本足夠時收斂 | 對 heavy-tail naive bootstrap 不一致 | ⚠️ §3 用 |

**Rust IMPL 推薦**：MAD 為主切點（§1 已用 `fee_bps_mad < 3.0` for calibrated），IQR 為 sanity check 並列。**避用** sample std（在 bimodal 下會誤判 dispersion，導致 grid_trading PostOnly 比例變動時 σ 跳動）。

### §2.3 「σ < 5 bps for calibrated」是否合理？

**結論：5 bps 太鬆，建議改 MAD < 3 bps**。

理由：
- Bybit linear default maker_fee = 2 bps、taker = 5.5 bps，spread = 3.5 bps
- 若 cell maker_fill_rate 穩定（接近 100% 或接近 0%）→ fee_bps spike 很窄 → MAD ≪ 1 bps
- 若 maker_fill_rate 在 30-70%（混合）→ MAD 約 1.5-2.0 bps（兩 spike 加權）
- MAD < 3 bps 篩出「fee 結構穩定 cell」（純 maker 或純 taker 或可預測混合）
- MAD ≥ 3 bps 表示 fee 結構不穩（VIP tier 切換、execution mode 切換、fee schedule 變動）— 不該標 'calibrated'

**MAD vs σ 換算**：對 normal 分布 σ ≈ 1.4826 × MAD；MAD < 3 → σ < 4.45 bps。比原 5 bps 嚴格但合理。

### §2.4 是否需要 bootstrap CI 替代 σ 切點？

**不需要 in label producer**。Bootstrap CI 用在 §3 的 ci_low/mid/high_bps 計算，是 simulated_fills row 的 metadata；label producer 自身用 MAD 即可（O(n log n) 計算，比 1000-iter bootstrap 快兩個數量級）。

但 bootstrap CI 在 §3 也不能 naive — 見 §3.2。

## §3. CI low/mid/high 計算法（V050 schema feed）

### §3.1 數學定義

對每 simulated_fill row 的 `net_bps_after_fee` 計算 confidence interval：

```
net_bps_after_fee = (exit_price - entry_price) / entry_price * 10000 * direction
                  - fee_bps  (entry side)
                  - fee_bps  (exit side)
                  - slippage_bps_estimate
```

**對 cell-level summary**（不是 per-fill）的三 percentile：

```
ci_low_bps  = percentile(net_bps_after_fee_distribution, 5)
ci_mid_bps  = percentile(net_bps_after_fee_distribution, 50)  // median
ci_high_bps = percentile(net_bps_after_fee_distribution, 95)
```

**CHECK 滿足**：percentile 函數定義保證 `p_5 ≤ p_50 ≤ p_95`，符合 V050 CHECK `ci_low_bps ≤ ci_mid_bps ≤ ci_high_bps`。

### §3.2 為何 percentile 而非 normal-based mean ± 1.96σ

理由：
1. **Web search 確認**：crypto returns 重尾（polynomially decay 而非 exponentially）；net_bps_after_fee 包含 returns → 同樣重尾
2. **mean ± 1.96σ 在重尾下**：低估 tail risk（normal 假設 99% 在 ±2.58σ；crypto 真實 99% 遠超此）
3. **percentile (empirical)**：直接從樣本經驗分布取，不假設形態
4. **與 V050 CHECK 自然一致**：percentile 單調必滿足 low ≤ mid ≤ high

### §3.3 樣本不足時的 fallback

```rust
fn compute_ci(net_bps_vec: &[f64]) -> (f64, f64, f64) {
    let n = net_bps_vec.len();
    if n < 30 {
        // 樣本太少，percentile 噪音大；用 median ± 0.6745*MAD（normal 50% interval extension）
        let median = median(net_bps_vec);
        let mad = mad(net_bps_vec);
        // 5/95 percentile under normal ≈ ±1.645σ；σ ≈ 1.4826*MAD
        let half_width = 1.645 * 1.4826 * mad;
        return (median - half_width, median, median + half_width);
    }
    if n < 200 {
        // 中等樣本：用 BCa (bias-corrected accelerated) bootstrap，B=1000
        // 但簡化版直接 empirical percentile + 寬 1.5x 補殘差不確定
        let p_5 = percentile(net_bps_vec, 5.0) - 0.5 * iqr(net_bps_vec);
        let p_95 = percentile(net_bps_vec, 95.0) + 0.5 * iqr(net_bps_vec);
        let p_50 = median(net_bps_vec);
        return (p_5.min(p_50), p_50, p_95.max(p_50));  // 強制單調
    }
    // n >= 200：直接 empirical percentile
    (percentile(net_bps_vec, 5.0), percentile(net_bps_vec, 50.0), percentile(net_bps_vec, 95.0))
}
```

**注**：n < 200 時用 normal-extension fallback 是工程妥協。**理論上正確**做法是 m-out-of-n bootstrap or BCa，但 Rust 端 IMPL 複雜度過高；此 fallback 在 limited 樣本下 CI 會略寬（保守方向），可接受。E1 IMPL 階段如有 BCa crate 可選用。

### §3.4 Bootstrap 不採用的理由

Naive percentile bootstrap 對重尾不一致（web search confirmed: "the conventional bootstrap of the mean from distributions in the domain of attraction of stable laws with infinite variance is not consistent"）。本 spec 用**直接 empirical percentile**（n ≥ 200）+ MAD-based normal extension（n < 30）+ inflated empirical percentile（30-200 中間區），全部規避 bootstrap consistency 問題。

## §4. Degraded Path — 'limited' tier 寫 'calibrated_replay' or 'synthetic_replay'

### §4.1 Decision: 'limited' → write `'calibrated_replay'`（不是 synthetic_replay）

### §4.2 理由（從 ML training data 安全性角度）

| 視角 | 'calibrated_replay' | 'synthetic_replay' |
|---|---|---|
| evidence_source_tier 語義 | 用真 demo+live_demo fills 校準 fee 模型 | 完全合成 walker，無真實 fill 基礎 |
| ML training data 適用 | ✅ ML 可用（CLAUDE.md §九 既登記）| ❌ 不可用（CLAUDE.md §九 既禁）|
| 'limited' 真實意義 | 樣本 30-199 + freshness OK + MAD 寬 → 真實但不確定大 | （與此情境無關，synthetic 不對應 limited）|
| MLDE/Dream consumer 行為 | 走 V051 Block B，含 expires_at TTL 守門 | 0 row，不進 ML 訓練 |

**核心邏輯**：
- `synthetic_replay` 是 Sprint A R3 synthetic walker 寫入 sentinel，**沒有真實 fill 基礎**
- `'limited'` calibration 雖樣本中等但**仍是真實 fills 校準**，本質與 'calibrated' 同類，僅統計信心稍低
- 把 'limited' 降級到 'synthetic_replay' = 把真實但不確定的數據混入無基礎合成數據池 — **錯誤分類**
- 正確做法：**保留 'calibrated_replay' tier 但設更短 expires_at TTL**（如 calibrated → 7d，limited → 3d），讓 V036 verify_replay_evidence_and_insert 的 expires_at hard check 自動降級資料生命週期

### §4.3 Rust IMPL 對應

```rust
fn label_to_tier(label: ExecutionConfidence) -> EvidenceTier {
    match label {
        Calibrated => EvidenceTier::CalibratedReplay,
        Limited    => EvidenceTier::CalibratedReplay,   // 同 tier，差別在 TTL
        None       => EvidenceTier::Discarded,           // 不寫 advisory
    }
}

fn label_to_ttl(label: ExecutionConfidence) -> Duration {
    match label {
        Calibrated => Duration::days(7),
        Limited    => Duration::days(3),
        None       => Duration::seconds(0),  // never inserted
    }
}
```

### §4.4 ML training data 安全性 cross-check

下游 mlde_demo_applier_evidence_filter Block B SQL：

```sql
WHERE replay_experiment_id NOT NULL
  AND manifest_hash NOT NULL
  AND expires_at > now()           -- TTL 自動降 limited 的可用窗
  AND status IN (...)
```

`expires_at` 短 TTL 把「limited 樣本只在 3d 內可信」這個信心衰減自動 enforce。MLDE 訓練端拉 row 時超過 TTL 自動篩掉，不需 consumer 端額外 logic。

## §5. Regime Detection — DEFER to Sprint D

### §5.1 Decision: DEFER

不在 R6 含 regime detection。Sprint D R9 sign-off 階段或更晚再評估。

### §5.2 理由

1. **黑名單避雷**：HMM regime detection 是 QC 黑名單第 1 條（profile 預載 + memory `feedback_indicator_lookahead_bias`）。任何 regime detection 提案 90% 滑入 HMM 或 GARCH，是 anti-pattern hot zone。
2. **Replication crisis 紅旗**（quant-strategy-design §Replication Crisis）：「我用 ML 找到 regime feature 預測 fee_bps」90% 是 leakage 或 overfitting；crypto 上 HMM regime 在 LUNA / FTX cascade 後普遍崩
3. **Hurst exponent / variance ratio test 的問題**：
   - Hurst > 0.5 trending / < 0.5 mean-reverting 在 1m timeframe noise 太大（QC half-life analysis: < 1 day signal 對 1m sampling rate 不匹配）
   - variance ratio test 對 sample size 敏感（要求 ≥ 500 obs），grid 1162 fills 勉強達標但 ma 635 fills + funding 99 fills 不行
4. **fee_bps regime 可能根本不存在**：
   - fee_rate 主要由 maker/taker (PostOnly TIF) + VIP tier (~穩定) 決定
   - regime（trending vs mean-reverting）影響 net_bps_after_fee 的 PnL 部分但不影響 fee_bps 本身
   - 若 R6 目標是校準 fee 模型，regime 是錯維度
5. **複雜度 vs marginal value**：R6 已有 sample count + freshness + MAD/IQR 三維度 boolean filter；加 regime 變 4 維度，combinatorial 切點 boundary 增 8 個 cell，IMPL 成本大、邊界 corner case 爆炸

### §5.3 何時 revisit

- Sprint D R9 reality-calibrated final sign-off 階段
- 或 ma_crossover edge 翻正後（5 策略內最有 regime-sensitive 的策略）
- 條件：(a) 有真實研究證明 regime 對 fee_bps 或 slippage_bps 的影響超過 sample std (b) 樣本 ≥ 500 per cell (c) 不採 HMM 而採 ATR-based regime gate（QC 黑名單替代方向）

## §6. 異常處理（Edge Cases）

| 情境 | label | 理由 |
|---|---|---|
| sample_count = 0 | None | trivial：無證據 |
| last fill = NULL / NaN timestamp | None | freshness 無法判定，fail-closed |
| σ / MAD = 0（all fills 同價同 fee） | **Calibrated 候選**（依 n + freshness） | 完全穩定的 fee（純 maker 或純 taker single mode）→ 高度可預測，正面信號；但仍須 n ≥ 200 + freshness OK |
| σ / MAD = NaN（n < 2） | None | 統計量無定義 |
| net_bps_after_fee 全 negative | label 不變（仍可 calibrated） | label 是 fee/slippage 校準信心，**不是 PnL 信心**；net 全負是策略 alpha 問題不是校準問題 |
| bootstrap CI fail (n < 30) | 走 §3.3 fallback (median ± 0.6745*MAD) | 不 fail-closed，給保守寬 CI |
| 部分 fills 有 NULL fee_rate | 過濾 NULL 後重算 n；n 低於切點降級 | DB 端應禁 NULL（trading.fills.fee_rate NOT NULL constraint），但 defensive |

## §7. Rust IMPL 邊界對齊（給 E1）

### §7.1 函數簽名

```rust
// rust/openclaw_engine/src/replay/calibration_label.rs（新檔，~120 LOC）

pub enum ExecutionConfidence {
    None,
    Limited,
    Calibrated,
}

#[derive(Debug, Clone)]
pub struct CalibrationResult {
    pub label: ExecutionConfidence,
    pub sample_count: usize,
    pub last_fill_age_ms: i64,
    pub fee_bps_mad: f64,
    pub fee_bps_iqr: f64,
    pub net_bps_p5: f64,
    pub net_bps_p50: f64,
    pub net_bps_p95: f64,
    pub ttl: chrono::Duration,
}

pub fn derive_execution_confidence(
    fills: &[FillRecord],
    now: chrono::DateTime<chrono::Utc>,
) -> CalibrationResult;
```

### §7.2 輸入欄位最小集（fills 端 column）

從 `trading.fills` 取：
- `id` (BIGINT, PK)
- `symbol` (TEXT)
- `strategy_name` (TEXT)
- `engine_mode` (TEXT, IN ('demo', 'live_demo')) — **必含兩者**（CLAUDE.md memory 既登）
- `fee_rate` (DOUBLE PRECISION) — fee_bps = fee_rate * 10000
- `entry_price` / `exit_price` / `direction` — for net_bps_after_fee
- `filled_at` (TIMESTAMPTZ) — for freshness
- `slippage_bps` 計算或 NULL — 若 schema 已存則用，否則由 R6-T2 IMPL 補

**Sample query (R6-T8 smoke test 用)**：
```sql
SELECT id, symbol, strategy_name, engine_mode, fee_rate,
       entry_price, exit_price, direction,
       filled_at,
       (exit_price - entry_price) / entry_price * 10000.0 * direction AS gross_bps
FROM trading.fills
WHERE strategy_name = $1
  AND symbol = $2
  AND engine_mode IN ('demo', 'live_demo')
  AND filled_at >= now() - INTERVAL '14 days'
ORDER BY filled_at;
```

### §7.3 輸出 enum 形態

`ExecutionConfidence` 需 `#[derive(Debug, Clone, Copy, PartialEq, Eq)]` + `serde::{Serialize, Deserialize}` 用於：
- 寫入 `replay.experiments.execution_confidence` (TEXT column, V049)
- payload jsonb 含 `{sample_count, last_fill_age_ms, fee_bps_mad, fee_bps_iqr}`
- writer 端 simulated_fills.ci_low/mid/high_bps 從 `CalibrationResult.net_bps_p5/p50/p95` 直取

### §7.4 錯誤處理

```rust
pub fn derive_execution_confidence(
    fills: &[FillRecord],
    now: DateTime<Utc>,
) -> CalibrationResult {
    // 空輸入 → None（不 panic 不 Result）
    if fills.is_empty() {
        return CalibrationResult::none_default(now);
    }
    // NaN balance / NaN fee_rate：filter out 後 n 自動降低
    let valid: Vec<&FillRecord> = fills.iter()
        .filter(|f| f.fee_rate.is_finite() && f.entry_price.is_finite())
        .collect();
    // ... 後續按 §1 邏輯
}
```

**不 return Result**：本 spec 採「downgrade-on-error」哲學，任何輸入異常 → 降至 None，不 propagate Err。理由：calibration label 是 advisory 信號不是執行門控，fail-closed 等同 'none'。

## §8. Acceptance Criteria 對應 Plan §7 A6/A7

| # | Acceptance | spec deliver |
|---|---|---|
| A6-1 | Fee model 不缺 | spec §1 維度 3 強制 fee_bps 統計算入；calibration_label.rs 必引 fee_rate；R6-T1 IMPL 端負責 mirror live 端 fee model |
| A6-2 | Calibration report includes sample count, freshness, confidence | `CalibrationResult` 含 `sample_count` + `last_fill_age_ms` + `fee_bps_mad`（信賴度 proxy）三項；writer R6-T5/T6 序列化進 payload.calibration jsonb + `replay.experiments.execution_confidence` |
| A7-1 | Weak sample auto-downgrade | `n < 30 → None` 強制（§1） |
| A7-2 | Sufficient sample → 'limited'/'calibrated' | grid_trading 1162 fills + freshness OK + 預期 MAD 達標 → 'calibrated'；ma_crossover 635 fills 同邏輯走 'limited' or 'calibrated' boundary（IMPL 端真值決定） |
| A7-3 | Stale auto-downgrade | `last_fill_age > 14d → None`（§1）；`> 7d but ≤ 14d → 至多 limited`（§1 第 2 維度切點對齊）|

額外貢獻 A6-5：CI 三 column percentile 計算（§3）天然滿足 V050 CHECK `ci_low ≤ ci_mid ≤ ci_high`。

## §9. Open Questions（IMPL 階段答）

1. **slippage_bps 計算端 R6-T2 IMPL 細節**：本 spec 把 slippage 視為已存在 column 或 R6-T2 補。若 R6-T2 採用 `Almgren-Chriss square-root impact` 模型（crypto-microstructure §5.3），需 volume_24h 輸入；若採固定 tier 表（`SLIPPAGE_TIERS` const 5 層 — QC memory 2026-04-24 既揭硬編碼），需確認 tier 分布是否 stale。**留 PA + E1 IMPL 階段決定**，本 spec 不 mandate。

2. **maker_fill_rate 跨 cell 變動**：CLAUDE.md §三 [33] 顯示 live_demo 7d maker fill rate 36.6%；不同 (strategy, symbol) 可能差異大（grid 高 maker / ma 低 maker）。本 spec MAD < 3 bps 切點假設 fee_bps 結構穩定；若某 cell maker_fill_rate 在 cell 內期間漂移 30% → 70%，MAD 可能 > 3 bps → 該 cell 自動降至 'limited'，是符合 spec 設計意圖（fee 不穩 → 信心降）。

3. **fee_rate column NULL handling**：SQL 應 enforce NOT NULL 但 defensive filter 在 §6 已寫；E1 IMPL 端確認。

4. **timezone 一致性**：last_fill_age 計算 `now - filled_at` 必雙端 UTC。`SET TIME ZONE 'UTC'` 在 PG 端，Rust 端 `chrono::Utc::now()`。確保不 drift。

## §10. 對抗性反問（5 條）

1. **Q: 樣本量翻倍 grid 從 1162 → 2400 fills，spec 結論變嗎？**
   A: n ≥ 200 切點下不變，仍 'calibrated'；但 MAD/IQR 估計更穩，CI 更窄。預期一致行為。

2. **Q: 換 OOS 7d → 換另一 7d 窗，spec 結論還對嗎？**
   A: 取決於另一窗 freshness + MAD：若另一窗距今 8d → 至多 'limited'（freshness 7d 切點）；若 PostOnly 部署改變了 maker_fill_rate 結構 → MAD 變動 → 可能降級。**這是 spec 設計意圖**：calibration 跟著真實 fee 結構動，stale 數據自動失效。

3. **Q: fee + 1bps（VIP tier 升級）結論還成立嗎？**
   A: fee_bps 整體 shift 1 bps 不影響 MAD 或 IQR（兩者是 location-invariant scale measures），label 不變。CI 上下移 1 bps 但結構不變。**正確 robustness**。

4. **Q: 若 grid_trading 某 symbol 的 fee_bps MAD = 5 bps（超 calibrated 切點），但 IQR = 6 bps（過 calibrated 8 bps 切點），怎判？**
   A: spec §1 用 `&&` 連接 MAD < 3 AND IQR < 8。MAD = 5 > 3 → calibrated_ok = false → 走 limited 路徑（MAD < 8 ✓ AND IQR < 20 ✓）→ 'limited'。**雙條件 AND 是設計**避免單一 metric outlier 誤推 calibrated。

5. **Q: 若 last fill 距今 7d 整（恰 boundary）怎判？**
   A: spec `last_fill_age_days <= 7.0`（含等號），7d 整算 calibrated；7.0001d 算 limited。E1 IMPL 用 `chrono::Duration::days(7)` 對應 168h，`<= 168.0 hours`。boundary 行為清晰。

## §11. 結論

**判定**：APPROVE — spec 可 deliver 給 R6-T4 E1 IMPL

**Key decisions**：
1. n=200/30 兩切點 + freshness 7d/14d + MAD 3/8 bps + IQR 8/20 bps 四維度 AND boolean filter
2. σ 用 MAD（bimodal-robust），不用 sample std；副驗用 IQR
3. CI 用 empirical percentile (n ≥ 200) + 寬幅 fallback (n < 200)，不用 naive bootstrap（重尾 inconsistency）
4. 'limited' tier → 'calibrated_replay' + 短 TTL（3d），不寫 'synthetic_replay'
5. Regime detection DEFER to Sprint D（避黑名單 + fee_bps 與 regime 弱相關）
6. 異常 fail-closed → 'None'（不 propagate Result）

**對 PA / E1 端 IMPL 邊界**：
- ~120 LOC 新檔 `replay/calibration_label.rs`
- 0 V### migration
- 0 schema 改動
- 0 既有 hot-path 邏輯改動
- IMPL 階段必跑 R6-T8 smoke test 對 grid + ma + funding + bb_breakout 4 strategy 跑全 spec，確認 reproducibility

**對 PM 的下一步**：
- Approve 此 spec → PA dispatch E1 Wave 1 (R6-T1/T2/T7) 並行 + PM 等 R6-T4 IMPL 後對 §1.1 表 4 strategy reproducibility 驗證

---

## Sources

- [A novel heavy tail distribution of logarithmic returns of cryptocurrencies - ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1544612321005250)
- [A Parametric Bootstrap for Heavy-Tailed Distributions - Cambridge](https://www.cambridge.org/core/journals/econometric-theory/article/abs/parametric-bootstrap-for-heavytailed-distributions/99AA8938F6B8A313D0B6F7EBA9B3B10F)
- [Bootstrap Methods for Statistical Inference - Extreme-Value Analysis](https://opensky.ucar.edu/system/files/2024-08/articles_23997.pdf)
- [Bootstrapping (statistics) - Wikipedia](https://en.wikipedia.org/wiki/Bootstrapping_(statistics))

---

QC ADVISORY DONE — pre-DAG R6-T0 deliverable
