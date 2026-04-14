//! ort (ONNX Runtime) backend stub — Stage 0 scaffold.
//! ort (ONNX Runtime) 後端骨架 — Stage 0。
//!
//! MODULE_NOTE (EN): Gated behind `edge_predictor_ort` feature (mutually
//!   exclusive with `edge_predictor_tract` per F8). Fallback backend if
//!   tract's ONNX opset coverage proves insufficient for LightGBM
//!   TreeEnsembleRegressor (see spec §7.1 precision-validation fallback).
//!   Adds ~60MB dynamic library; only swap to this backend if CC harness
//!   detects tract precision failure >= 1e-3 or NaN/Inf output.
//! MODULE_NOTE (中): `edge_predictor_ort` feature 門控（與 `edge_predictor_tract`
//!   互斥，F8）。tract 精度不足時的後備後端；引入 ~60MB 動態庫，只有 CC harness
//!   偵測到 tract 精度誤差 ≥ 1e-3 或 NaN/Inf 輸出時才切換此後端。
//!
//! Mac note (spec §7.1 housekeeping): ort ships as a macOS dylib; bundling
//! guidance is TBD pending Stage 2 decision.
//! Mac 註記（規格 §7.1 housekeeping）：ort 在 macOS 為 dylib；打包方針待 Stage
//! 2 決定。
//!
//! Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4 §7.1

// NOTE: empty stub — real implementation lands in Stage 2 with:
//   - ort 2.x dependency
//   - load_from_path(&Path) + ort::Session builder
//   - EdgePredictor impl delegating to ort runtime
//   - NaN/Inf output guard (return Err(InferenceFailed(...)))
//
// NOTE: 空殼 — 實作將於 Stage 2 引入 ort 依賴並落地模型載入 + 推理。
