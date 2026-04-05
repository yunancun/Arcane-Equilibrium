"""
ML Training Pipeline — LightGBM Scorer + ONNX export for OpenClaw.
ML 訓練管線 — OpenClaw 的 LightGBM 評分器 + ONNX 導出。

MODULE_NOTE (EN): Phase 2 training infrastructure. Modules:
  - label_generator: net_pnl/ATR label with winsorization + ATR_FLOOR
  - scorer_trainer: LightGBM regression with CPCV + embargo
  - calibration: Isotonic regression + Gaussian smoothing (ECE < 0.05)
  - onnx_exporter: LightGBM → ONNX with f32 cast + NaN sentinel
  - leakage_check: Feature whitelist validation
MODULE_NOTE (中): Phase 2 訓練基礎設施。
"""
