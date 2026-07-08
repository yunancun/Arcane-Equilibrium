---
name: restart_all.sh --rebuild 只重建 engine binary（單一產物 cargo build）
description: --rebuild 觸發原生 rebuild（cargo build --release -p openclaw_engine）而非純 restart；部署 Rust engine fix 直接 --rebuild 即可
type: feedback
originSessionId: 258747c1-ad4c-4e68-89b4-57dab2c6a8e0
---
`bash helper_scripts/restart_all.sh --rebuild` 會 `cargo build --release -p openclaw_engine`（`--manifest-path rust/Cargo.toml`）重建 `rust/target/release/openclaw-engine` binary，再重啟服務。**不帶 `--rebuild` = 純重啟，跑既有 binary**。`--rebuild` 是唯一觸發原生重建的旗標。engine 為 standalone binary，Python 經 IPC（Unix socket）連接，非 Python extension，故 `--rebuild` 只有 engine binary 這一個建構產物。

**Why**：部署 Rust engine 代碼改動一律用 `--rebuild`；不重建則新 PID 起來、log 重置，看似換了 binary，實際仍跑舊 binary（2026-04-14 FA-PHANTOM-1 事故：canary 立刻看到舊行為，差點誤判修復無效）。

**How to apply**：
- **部署 Rust engine 改動**：`bash helper_scripts/restart_all.sh --rebuild`（先編 binary，失敗不 kill 既有服務）。
- **只想重啟不重建**：省略 `--rebuild`，跑既有 binary。
- **驗證**：部署後 `ls -la rust/target/release/openclaw-engine` mtime 應晚於要部署的 commit 時間戳 — 最可靠的「真的換 binary 了嗎」single-source-of-truth。

> 2026-07-09 校正：PyO3 已於 2026-04-20（PYO3-ELIMINATE-1 Phase 3, `9b691a0`）全數移除；`--rebuild` 現只 `cargo build --release -p openclaw_engine`，無 wheel。
