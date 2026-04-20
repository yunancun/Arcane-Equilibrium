---
name: ML/DL 自主學習架構設計
description: ML/DL 驅動的 Agent 自主學習架構 v0.4 設計草稿，經 QC+MIT+FA 三方審查，待打磨後實施
type: project
---

ML/DL 驅動的 Agent 自主學習架構設計草稿 v0.4（2026-04-03）。

**Why:** 現有「學習」只是記賬（AnalystAgent 統計勝率→微調權重±0.1），三個未接線模組都在優化 SL/TP 而非策略信號參數。需要真正的學習閉環。

**核心設計（已確認）：**
- Teacher-Student：Claude 週度出 Learning Directive / Local ML (LightGBM) 做信號評分 / Bayesian Optimizer (Optuna) 做參數優化
- 語言分層：訓練 Python / 推理 Rust ONNX (ort crate) / 橋接 PyO3
- DL 僅三場景：Symbol Embedding (Autoencoder) / Regime Detection (LSTM) / 時序基礎模型 (TimesFM/Chronos)
- 探索機制：Thompson Sampling + LinUCB（MIT 教授評為最大單項改進）
- 跨幣遷移：James-Stein 部分池化（非完整分層貝葉斯）
- 5 階段 ~13-18 週

**How to apply:** 設計文件在 `docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md`，TODO.md 有 ML-1a~ML-1h 待打磨項。不急於實施，先繼續深入研究。
