---
name: data-drift-detection
description: 資料漂移偵測 — Distribution shift / Concept drift / Population Stability Index (PSI) / KL divergence / KS test / Wasserstein distance；live 階段 ML 模型監控 SOP。MIT agent 主用。
allowed-tools: Read, Grep, Glob, Bash
---

# Data Drift Detection（資料漂移偵測手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

## 何時觸發

- MIT 收到「Live 階段 ML 模型表現衰減」「為何 model accuracy 從 80% 掉到 60%」「regime 切換偵測」
- ML 模型上線後每週例行 drift check
- regime change 顯著事件（如 Fed 大幅升降息、crypto crash、大 listing）後重新 audit
- model_registry V023 的 production model 持續監控

## ★ 黃金法則

**ML 模型 live 表現衰減 = drift / regime 切換 / leakage / 資料管線壞**。前三者要 drift detection 工具區分。
**Drift 不必然 = 重訓**：先判斷 drift 性質，再決定動作（重訓 / 換特徵 / 暫停 model）。

## 1. Drift 三種類型

### 1.1 Covariate Drift（X 分布變了）
- `P(X)` 變動但 `P(y|X)` 不變
- 例：BTC 價從 30k 漲到 60k，volatility regime 變但 「strategy logic on X」 仍對
- 偵測：feature 分布監控

### 1.2 Concept Drift（X→y 關係變了）
- `P(y|X)` 變動
- 例：QE 期間「funding > 0.1% → 後續 mean revert」現在不成立
- 偵測：模型 prediction error rate 上升 + feature 分布未變

### 1.3 Label Drift（y 分布變了）
- `P(y)` 變動
- 例：原本 50/50 long/short label 變 30/70
- 偵測：label histogram 對比

OpenClaw 經驗：crypto 主要面對 covariate + concept drift，label drift 較罕見（除非 regime 從 trending → ranging）。

## 2. 偵測指標對照表

| 指標 | 適用 | 公式 / 概念 | 閾值 |
|---|---|---|---|
| **PSI** (Population Stability Index) | 連續 / 分組 feature 分布 | Σ (P_curr − P_ref) × ln(P_curr / P_ref) | < 0.1 穩定 / 0.1-0.25 警告 / > 0.25 漂移 |
| **KL Divergence** | 連續分布相對熵 | Σ P_curr × ln(P_curr / P_ref) | 沒有絕對閾值，看趨勢 |
| **KS Test** (Kolmogorov-Smirnov) | 連續分布 hypothesis test | sup\|F_curr(x) − F_ref(x)\| | p < 0.05 = drift |
| **Wasserstein Distance** | Earth-Mover's distance | min cost transport between distributions | 數值依 feature scale |
| **Chi-squared** | 類別 feature | Σ (O−E)²/E | p < 0.05 = drift |
| **JS Divergence** | KL 對稱版 | (KL(P\|M) + KL(Q\|M))/2 with M=(P+Q)/2 | 範圍 [0, ln 2] |

### PSI 詳細
```python
import numpy as np

def psi(reference, current, bins=10):
    bin_edges = np.percentile(reference, np.linspace(0, 100, bins+1))
    ref_dist, _ = np.histogram(reference, bins=bin_edges)
    cur_dist, _ = np.histogram(current, bins=bin_edges)
    
    # avoid zero division
    ref_pct = (ref_dist + 1e-9) / sum(ref_dist + 1e-9)
    cur_pct = (cur_dist + 1e-9) / sum(cur_dist + 1e-9)
    
    return np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct))
```

## 3. 監控架構

### 3.1 三組對照
- **Reference**：training set 分布（fixed）
- **Production**：live 最新 N hour 資料
- **Last week**：上週同期（trend）

### 3.2 監控頻率
| 用途 | 頻率 |
|---|---|
| Per-feature distribution | 每 hour |
| Model prediction distribution | 每 5 min |
| Per-segment（per symbol / strategy）| 每 day |
| Regime indicator（vol / funding / spread）| 每 5 min |

### 3.3 警報門檻
- Single feature PSI > 0.25 → warning
- ≥ 3 features PSI > 0.25 同時 → critical
- KS test p < 0.01 持續 1 hour → critical

## 4. Concept Drift 偵測

### 4.1 直接法：error rate monitoring
- live prediction error 比 OOS error 高 > 50% → concept drift 警報
- 用 `passive_wait_healthcheck` cron 每 6h 跑

### 4.2 間接法：DDM (Drift Detection Method)
- 偵測 error rate 的 mean + std 變化
- 觸發後 alert + 進入 retraining queue

### 4.3 間接法：Page-Hinkley test
- 累計偏差超門檻觸發

## 5. Drift 後的動作決策樹

```
1. Drift 偵測 → severity 分級
2. severity 低（PSI 0.1-0.25 single feature）：
   → 繼續觀察，每天重 check
3. severity 中（PSI > 0.25 single 或多 feature warning）：
   → 暫停 model 寫倉位（shadow mode）
   → 7d 內重訓計劃
4. severity 高（多 feature critical 或 prediction error rate 飆）：
   → 立即下線 model（fallback 到 baseline strategy）
   → 24h 內 RCA：drift type / regime change / data pipeline?
   → 修復後重訓 + canary 重新部署
```

## 6. OpenClaw 特定 drift signals

### 6.1 Crypto regime indicators
| Indicator | 監控 | drift 信號 |
|---|---|---|
| BTC realized vol (24h) | 每 5 min | > 90 percentile → vol regime shift |
| Funding rate avg | 每 5 min | -0.3% / +0.3% extreme → settlement-time pump |
| Spread (top-of-book) | 每 5 min | > 0.5% sustained → liquidity crisis |
| Open Interest change | 每 5 min | > 20% in 1h → cascade event |
| Cross-symbol correlation | 每 hour | > 0.9 spike → risk-off sync |

### 6.2 OpenClaw model-specific drift
- `bb_breakout` features：squeeze_bw / expansion_bw 分布變動 → regime shift
- `exit_features.giveback_atr_norm`：分布變動 → ATR scale 是否再 broken
- `edge_estimator` cells：grand_mean shift > 30 bps → 全策略需重評

## 7. 工作流（10 步）

1. **設定 reference window**（training set period）
2. **設定 current window**（last 24h / 7d）
3. **逐 feature 算 PSI / KS / Wasserstein**
4. **逐 segment 算同樣指標**（per symbol / per strategy）
5. **prediction distribution drift**（KS test on score）
6. **Error rate drift**（DDM / Page-Hinkley）
7. **Regime indicator 監控**
8. **Aggregate severity**（low / medium / high）
9. **Decision tree 觸發動作**
10. **報告 + memory update**

## OpenClaw 特定核心

- **engine_mode IN ('live', 'live_demo')**：reference 和 current 都必須這個 filter
- **passive_wait_healthcheck.py**：drift check 應加為 check_data_drift_X()，cron 6h 跑
- **edge_estimator schedule**：grand_mean 是 implicit drift indicator
- **CognitiveModulator.confidence_floor**：drift 觸發後可動態抬高 floor 降倉
- **Phase 5 reframed 策略 edge 為負**：當前 model 都還在 Skeleton/Foundation，drift 監控基建先建好但不急用

## 反模式（見即 Reject）

- 沒 reference window → 沒比對基準
- 只看 single PSI 閾值 0.25 → 忽略多 feature 累積警報
- 沒 per-segment 監控 → 整體看穩但 ETHUSDT drift
- error rate 上升不查 drift（只看絕對值）
- drift 警報後立即 retrain（不先判斷 type）
- 沒 fallback baseline strategy → 下線 model 後系統 idle
- 用 normal 假設算 KS（crypto fat tail）

## 輸出格式

```markdown
# MIT Data Drift Audit — <model> · <date>

## Reference / Current windows
- ref: [t0, t1] (training set)
- curr: [now-24h, now]

## Per-feature drift
| Feature | PSI | KS p | Wasserstein | severity |

## Per-segment drift
| Segment | top drift feature | severity |

## Prediction distribution drift
KS p: X / drift: Y/N

## Error rate drift
| Window | error rate | DDM trigger |

## Regime indicators
| Indicator | current | percentile | signal |

## Aggregate severity
low / medium / high

## 建議動作
（依 §5 decision tree）

MIT AUDIT DONE: <report_path>
```
