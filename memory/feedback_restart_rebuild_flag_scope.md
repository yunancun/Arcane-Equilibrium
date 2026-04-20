---
name: restart_all.sh --rebuild 現在會同時重建 engine binary + PyO3（2026-04-14 後）
description: --rebuild 在 2026-04-14 FA-PHANTOM-1 事故後已修 — 現先 cargo build engine binary 再 rebuild PyO3；部署 Rust engine fix 直接 --rebuild 即可
type: feedback
originSessionId: 258747c1-ad4c-4e68-89b4-57dab2c6a8e0
---
`bash helper_scripts/restart_all.sh --rebuild` 現在（2026-04-14 後）會同時：(a) `cargo build --release -p openclaw_engine` 重建 engine binary，(b) `build_pyo3.sh` 重建 PyO3 wheel 並雙寫 `.so` 到兩個 venv。

**Why**：2026-04-14 FA-PHANTOM-1 deploy 翻車 — 當時 `--rebuild` 只調用 `build_pyo3.sh`（只重 PyO3 wheel，不動 engine binary）。跑了 `restart_all.sh --rebuild` 後，新 PID 起來了、engine.log 也重置了，看起來像新 binary，但 `ls -la rust/target/release/openclaw-engine` 顯示 mtime 20:26（早於 fix commit 22:41），即仍是 pre-fix binary。Canary 立刻看到 4 次 `FAST_TRACK CloseAll fired risk_level=Normal`，差點誤判修復無效。根因確認為腳本語意與操作者期待不符。

**How to apply**：
- **新流程（推薦）**：部署 Rust engine 或 PyO3 代碼改動，一律 `bash helper_scripts/restart_all.sh --rebuild`。新腳本先編 engine binary，再編 PyO3 wheel，任一失敗不 kill 既有服務。
- **驗證**：部署後 `ls -la rust/target/release/openclaw-engine` mtime 應晚於要部署的 commit 時間戳 — 仍是最可靠的「真的換 binary 了嗎」single-source-of-truth。
- **只改 PyO3 struct ABI**：仍可用 `--rebuild`，engine binary 會一起編但不耗太多（增量）。如真需只編 PyO3，手動 `bash helper_scripts/build_pyo3.sh`。
- **只改 engine 代碼**：`--rebuild` 仍是最簡路徑；如想跳過 PyO3 可手動 `cargo build --release -p openclaw_engine --manifest-path rust/Cargo.toml && restart_all.sh --engine-only`。

**陷阱曾經存在於**：commit 之前，pre-fix 的 restart_all.sh（2026-04-14 21:00 之前 checkout）。如歷史 session 或 rollback 回到該版本，`--rebuild` 語意會回退。
