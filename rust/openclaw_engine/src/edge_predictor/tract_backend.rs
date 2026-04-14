//! tract-onnx backend stub — Stage 0 scaffold.
//! tract-onnx 後端骨架 — Stage 0。
//!
//! MODULE_NOTE (EN): Gated behind `edge_predictor_tract` feature (mutually
//!   exclusive with `edge_predictor_ort` per F8). This file is an empty
//!   placeholder until Stage 2 (ML-MIT) adds the `tract-onnx` dependency to
//!   Cargo.toml and implements model loading + inference. The gating ensures
//!   default `cargo build` / `cargo check` never pulls tract-onnx.
//! MODULE_NOTE (中): `edge_predictor_tract` feature 門控（與 `edge_predictor_ort`
//!   互斥，F8）。當前為 Stage 0 占位；Stage 2 ML-MIT 添加 `tract-onnx` 依賴並實
//!   現模型載入 + 推理。默認 build 不會拉取 tract-onnx。
//!
//! Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4 §7.1

// NOTE: empty stub — real implementation lands in Stage 2 with:
//   - tract-onnx 0.21 dependency (default-features off, features=["onnx"])
//   - load_from_path(&Path) -> Result<TractPredictor, TractError>
//   - EdgePredictor impl delegating to tract-rs runtime
//   - Schema hash validation on load (fail-fast if mismatch)
//   - Inference hot path: InlineBuf<[f32; 17]> → into_shape(&[1, 17, 1])
//     → run_plan → extract [q10, q50, q90] from output
//
// NOTE: 空殼 — 實作將於 Stage 2 引入 tract-onnx 依賴並落地模型載入 + 推理。

// Intentional no-op module body; keeping the file so lib.rs / mod.rs keep
// the `pub mod tract_backend` declaration valid under the feature flag.
// 有意保留空模組體，讓 feature flag 下的 `pub mod tract_backend` 宣告有效。
