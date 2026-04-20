---
name: Future Mac Deployment Target
description: Confirmed future target is Apple Silicon Mac (M5 Ultra or M5 Max); shapes CI tuple choices and ONNX runtime assumptions
type: project
originSessionId: e658c1ef-0aa7-451b-9716-b76e1b29acfb
---
Operator 確認未來部署目標為 **Apple Silicon Mac**，預計 **M5 Ultra 或 M5 Max**（2026-04-15 操作員確認）。

**Why:**
- `CLAUDE.md §7` 已要求「項目必須隨時可以部署在 macOS 上運行」；此記憶把抽象要求變成具體硬件鎖定
- 影響 CI target tuple 選擇：`aarch64-apple-darwin`（必）— **不是** `aarch64-unknown-linux-gnu`（Linux-on-ARM，與 macOS ARM 是不同 platform tuple，常被混為一談）
- M5 Ultra/Max 預期高統一記憶體（延續 M2/M3/M4 Ultra 的 64-256GB unified memory 趨勢）+ Neural Engine + Metal — 未來有機會加速 ONNX inference，但當前設計不依賴（tract-onnx 純 CPU 已足）

**How to apply:**
- 任何新增 CI matrix 時默認加 `macos-14` / `macos-15` runner（GitHub Actions 自 2024 已是 Apple Silicon 默認）
- 引入 Rust crate 前檢查 `aarch64-apple-darwin` 支援（可能卡的：某些 C FFI / SIMD intrinsics / CUDA-only crate）
- ONNX runtime 選擇：tract-onnx 跨平台純 Rust 為主線，`ort` 在 macOS 需捆 `libonnxruntime.dylib` — 若 Stage 2 切 ort，macOS 部署需補 bundling 步驟
- 服務部署腳本（當前 systemd）需有 launchd 遷移路徑
- 不要引入 `x86_64`-only 假設（SSE/AVX intrinsics 需 #[cfg] 守衛）
- Python 依賴避免 Linux-only 擴展（`psutil` Linux-specific API、`epoll`-only async stack 等）
- EDGE-P3-1 v1.3 CC #10 已強制 `aarch64-apple-darwin` build + precision + ArcSwap concurrent test

**Decision：linux-arm64 支援延後**
QA-E6 在 EDGE-P3-1 round-2 提了 `aarch64-unknown-linux-gnu` CI，已延後 W24+。操作員未來走 Mac，linux-arm64（NAS/Pi 等）不在主目標路徑上。未來 40TB NAS 若升級 ARM controller 再議。
