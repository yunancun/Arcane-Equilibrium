---
name: data-drift-detection
description: MIT agent 主用：懷疑 live ML 模型輸入分布漂移、預測質量退化、或設計 drift 監控時讀。
allowed-tools: Read, Grep, Glob, Bash
---

# Data Drift Detection（資料漂移偵測手冊）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：covariate/concept/label drift 分類、PSI/KL/KS/Wasserstein/JS/Chi² 公式、DDM/Page-Hinkley 不在本檔重述；本檔只列本專案的閾值判準、監控接線與 SSOT 指針。

## 何時觸發

- MIT 收到「Live 階段 ML 模型表現衰減」「accuracy 掉」「regime 切換偵測」
- ML 模型上線後每週例行 drift check；顯著 regime 事件後重新 audit
- model_registry 的 production model 持續監控

## ★ 黃金法則

**ML live 表現衰減 = drift / regime 切換 / leakage / 資料管線壞**，用 drift detection 工具區分前三者。
**Drift 不必然 = 重訓**：先判斷 drift 性質，再決定動作（重訓 / 換特徵 / 暫停 model）。
OpenClaw 經驗：crypto 主要面對 covariate + concept drift；label drift 較罕見（除非 regime 從 trending → ranging）。

> ⚠️ **執行需求**：PSI / KS / Wasserstein 計算需 Python 套件（scipy / sklearn / numpy）；無 venv → 協調 E1 跑或在 Linux runtime 跑。

## 1. 專案閾值判準

- PSI：業界 default < 0.1 穩定 / 0.1-0.25 警告 / > 0.25 漂移（**建議起點，非治理硬規範**；依 model + symbol 動態調整）
- KS test p < 0.05 = drift；KL / Wasserstein 看趨勢無絕對閾值
- 警報門檻：single feature PSI > 0.25 → warning；**≥ 3 features PSI > 0.25 同時 → critical**；KS p < 0.01 持續 1 hour → critical
- crypto fat tail：不可用 normal 假設算檢定

## 2. 監控架構

三組對照：**Reference**（training set 分布，fixed）/ **Production**（live 最新 N hour）/ **Last week**（上週同期 trend）。

| 用途 | 頻率 |
|---|---|
| Per-feature distribution | 每 hour |
| Model prediction distribution | 每 5 min |
| Per-segment（per symbol / strategy）| 每 day |
| Regime indicator（vol / funding / spread）| 每 5 min |

Concept drift：live prediction error 比 OOS error 高 > 50% → 警報；用 `helper_scripts/db/passive_wait_healthcheck.py` cron 每 6h 跑；DDM / Page-Hinkley 靠內建知識。

## 3. Drift 後的動作決策樹

```
1. Drift 偵測 → severity 分級
2. 低（PSI 0.1-0.25 single feature）：繼續觀察，每天重 check
3. 中（PSI > 0.25 single 或多 feature warning）：暫停 model 寫倉位（shadow mode）+ 7d 內重訓計劃
4. 高（多 feature critical 或 prediction error rate 飆）：
   → 立即下線 model（fallback 到 baseline strategy）
   → 24h 內 RCA：drift type / regime change / data pipeline?
   → 修復後重訓 + canary 重新部署
```

## 4. OpenClaw 特定 drift signals

### 4.1 Crypto regime indicators
| Indicator | 監控 | drift 信號 |
|---|---|---|
| BTC realized vol (24h) | 每 5 min | > 90 percentile → vol regime shift |
| Funding rate avg | 每 5 min | -0.3% / +0.3% extreme → settlement-time pump |
| Spread (top-of-book) | 每 5 min | > 0.5% sustained → liquidity crisis |
| Open Interest change | 每 5 min | > 20% in 1h → cascade event |
| Cross-symbol correlation | 每 hour | > 0.9 spike → risk-off sync |

### 4.2 Model-specific drift（不在本 skill 列具體 feature）
各 model / strategy 特定 drift signal 隨策略增刪 + feature 演進變動，**本 skill 不寫死**。通用模式（不會 drift）：對每個 production model 列 top-3 high-importance features → 逐個算 PSI + KS p-value → 異常即 alert。具體 feature 列表由 audit 開始時 grep `learning.X_features` schema + `feature_importance` query 取真值。

## 5. 工作流（10 步）

1. 設定 reference window（training set period）→ 2. 設定 current window（last 24h / 7d）→ 3. 逐 feature 算 PSI / KS / Wasserstein → 4. 逐 segment 同指標（per symbol / strategy）→ 5. prediction distribution drift（KS on score）→ 6. Error rate drift（DDM / Page-Hinkley）→ 7. Regime indicator 監控 → 8. Aggregate severity → 9. Decision tree 觸發動作 → 10. 報告。

## 穩定 drift rule（不會 drift）

reference + current 兩個 window 都必 `engine_mode IN ('live','live_demo')` filter；drift check 必加 `helper_scripts/db/passive_wait_healthcheck.py:check_data_drift_X()`（cron 6h）；CognitiveModulator confidence_floor 是動態降倉機制（架構級不變）。

## 反模式（見即 Reject）

- 沒 reference window → 沒比對基準
- 只看 single PSI 閾值 0.25 → 忽略多 feature 累積警報
- 沒 per-segment 監控 → 整體看穩但單 symbol drift
- error rate 上升不查 drift（只看絕對值）
- drift 警報後立即 retrain（不先判斷 type）
- 沒 fallback baseline strategy → 下線 model 後系統 idle
- 用 normal 假設算 KS（crypto fat tail）

## 輸出格式

```markdown
# MIT Data Drift Audit — <model> · <date>

## Reference / Current windows
- ref: [t0, t1] (training set)；curr: [now-24h, now]

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
（依 §3 decision tree）

MIT returns an immutable `role_fragment_v1` with `payload_kind=finding_fragment_v1` for the task closure; no automatic report or memory append.
```
