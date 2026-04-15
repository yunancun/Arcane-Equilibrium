---
title: EDGE-P3-1 Backend Selection — tract-onnx vs ort
date: 2026-04-15
status: Decision Confirmed (Stage 2 pending artifact)
spec: docs/references/2026-04-15--edge_predictor_spec.md §7.1 (C10, F8, AI-E E5)
owner: AI-E (Rust inference side)
---

# EDGE-P3-1 Backend Selection Audit

## 1. Decision (unchanged, confirming spec §7.1)

**Primary backend**: `tract-onnx 0.21` (pure Rust, `default-features = false`, `features = ["onnx"]`).
**Fallback backend**: `ort 2.x` (ONNX Runtime dylib bindings).
**Mutual exclusion**: enforced at compile time via `compile_error!` in
`edge_predictor/mod.rs` lines 25–30 (F8).
**Default build**: null_backend (`Err(NoModel)` → shrinkage fallback); tract and ort
feature flags pull no deps in the current Cargo.toml because both backend source
files are empty stubs until Stage 2. See §5 below for the exact Cargo diff to
land alongside the Stage 2 artifact.

## 2. Selection Criteria (already in spec; logged for CC §15 traceability)

| Dimension | tract-onnx 0.21 | ort 2.x | Winner |
|---|---|---|---|
| Binary size | +3.5MB (pure Rust) | +60MB (libonnxruntime dylib) | tract |
| macOS packaging | No-op (static) | Dylib bundling TBD (AI-E E5 housekeeping) | tract |
| Cross-compile | Trivial via `aarch64-apple-darwin` | Requires prebuilt dylib per target | tract |
| Opset coverage (`ai.onnx.ml.TreeEnsembleRegressor` v1/v3) | Supported per AI-E spec §7.1 L486 | Full ONNX reference | tie |
| Historical correctness on LGBM TreeEnsembleRegressor | ML-MIT flag: missing-value handling + late operators | Reference implementation | ort |
| CI matrix impact | linux-x86_64 + aarch64-apple-darwin single pass | Extra dylib artifact step | tract |
| Runtime | ~80–150µs per predict (spec §7.6 target <1ms) | Comparable | tie |
| Operational familiarity | Emerging | Mature upstream | ort |

`tract` wins on 5 axes, loses on 1 (historical correctness → why ort is kept as
fallback, not abandoned).

## 3. Switch Runbook — Stage 2 Precision Fail → ort

Trigger: **CC harness** (1000 random FeatureVectorV1 instances) reports any of:
- `max_abs_err(tract_pred, python_lgbm_pred) >= 1e-3` for any of q10/q50/q90, OR
- any NaN/Inf in tract output across the 1000 vectors.

Switch steps (do not skip):

1. File `docs/audits/YYYY-MM-DD--edge_predictor_tract_precision_fail.md` with:
   - raw 1000-vector diff histogram + worst 10 rows.
   - root cause hypothesis (e.g. `missing_value` handling, late opset).
2. Flip `Cargo.toml` default alias:
   ```toml
   edge_predictor = ["edge_predictor_ort"]  # was edge_predictor_tract
   ```
3. `cargo build --no-default-features --features edge_predictor_ort` and confirm
   `compile_error!` does NOT fire (sanity check for F8 guard).
4. Re-run CC harness with ort backend; require `max_abs_err < 1e-3` AND
   `coverage_error < 3pp` before proceeding. If ort also fails, halt promotion
   and escalate — do NOT ship either backend.
5. macOS: land AI-E E5 housekeeping concurrently — libonnxruntime dylib
   bundling steps (install_name_tool rewrite + `@rpath` + code-signing). Until
   Mac deploy is active, Linux-only ort ship is acceptable.
6. Update V014 audit log with backend switch event (`event_type =
   'edge_predictor_backend_switch'`, `from = 'tract'`, `to = 'ort'`,
   `reason_code = 'precision_fail_1e-3'`).

## 4. Residual Risks (to watch at Stage 2)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| tract 0.21 silently mis-evaluates a late LGBM operator | Medium | High (wrong edge predictions → risk-config miscalibration) | CC harness 1000-vector diff + coverage test before any promote |
| `onnxmltools` < 1.12 emits quantile with a known bug | Low (pinned) | High | spec §7.1 pin already landed; CC verifies with version check |
| ort macOS dylib bundling regresses on CI matrix change | Medium | Medium | AI-E E5 housekeeping must land before Mac deploy; linux-only ort is safe until then |
| Operator enables both feature flags by accident | Already mitigated | N/A | F8 `compile_error!` in `edge_predictor/mod.rs` |

## 5. Cargo.toml Diff (ready for Stage 2 artifact landing)

Current (scaffolding only):

```toml
[features]
default = []
edge_predictor_tract = []
edge_predictor_ort = []
```

Stage 2 target (verbatim per spec §7.1):

```toml
[dependencies]
tract-onnx = { version = "0.21", default-features = false, features = ["onnx"], optional = true }
ort = { version = "2", optional = true }

[features]
default = []
edge_predictor_tract = ["dep:tract-onnx"]
edge_predictor_ort = ["dep:ort"]
edge_predictor = ["edge_predictor_tract"]  # default alias
```

Defer until ML-MIT ships the ONNX artifact; pulling either dep today adds
compile time with zero benefit because both backend files are empty stubs.

## 6. Open Follow-ups (not blocking Phase B)

- [ ] **CC harness implementation** — 1000-vector tract↔Python diff scaffolding
  (CC §15 task #28). Blocked only on ML-MIT first ONNX export.
- [ ] **macOS CI matrix entry** — `aarch64-apple-darwin` build of
  `edge_predictor_tract`; does not need ort unless/until Stage 2 swaps.
- [ ] **ort dylib bundling SOP** — document `install_name_tool` + `@rpath`
  rewrite steps; deferred until tract precision actually fails.

---

**Conclusion**: decision documented in spec §7.1 holds. No new evidence
warrants revisiting. Stage 2 lands tract-onnx first; ort is the contingency
and stays as a one-line Cargo flip plus a documented runbook.

簡短中文總結：spec §7.1 已定 tract-onnx 先行、ort 為精度後備。本 audit
覆核決策仍然 sound，列出切換 runbook（1000-vector max_abs_err ≥ 1e-3 →
翻 Cargo default alias → ort → V014 審計記錄）。Stage 2 artifact 到位前
不改 Cargo.toml，避免拉無用依賴。
