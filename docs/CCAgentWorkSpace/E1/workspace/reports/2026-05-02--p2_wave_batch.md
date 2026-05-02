# E1 P2 Wave Batch — 4 Fast-Win 一輪修復（2026-05-02）

## 任務

CC Step 2 cold audit 結出 4 fast-win → operator 一輪派發 E1 合修：
- **MIT-S2-6** (P3): `opportunity_tracker.persist_regret_summary` noise INSERT 早停
- **E3-S2-P2-1** (P2): `/strategy/prelive/edge-gates` exception class+message JSON envelope 漏
- **E3-S2-P2-2** (P2): `/live/close-position` `IPC error: {exc}` HTTPException detail 漏
- **PA-DRY-1** (P3): Rust `is_legacy_close_tag` 4-行 prefix chain 兩處重複

## 修改

5 個檔（Fix 4 跨 commands.rs + mod.rs）：

| file | LOC delta |
|---|---|
| program_code/local_model_tools/opportunity_tracker.py | +17/-0 |
| .../control_api_v1/app/strategy_read_routes.py | +9/-2 |
| .../control_api_v1/app/live_session_account_routes.py | +7/-2 |
| rust/openclaw_engine/src/tick_pipeline/mod.rs | +16/-0（新 helper） |
| rust/openclaw_engine/src/tick_pipeline/commands.rs | +6/-12（兩處 dedup） |

淨 +39 行（含雙語注釋）；hot-path Rust 實質碼數不變但更乾淨。

## 驗證

- `cargo test --release -p openclaw_engine --lib` → 2404 PASS / 0 FAIL（baseline）
- `cargo test --release -p openclaw_engine --tests` → 2560 PASS / 0 FAIL（baseline）
- `pytest control_api_v1/tests/` → 3256 PASS / 10 SKIP / 0 FAIL（step-1 已 +1）
- `pytest ml_training/tests/test_mlde_shadow_advisor.py` → 5 PASS（Fix 1 不破）
- `git diff --check` → 0 whitespace issue
- `git status --short` → 5 expected files + 2 operator-WIP（CLAUDE.md / TODO.md）非本批

## 治理

- 雙語注釋（CLAUDE.md §七）：4 處新代碼全 ✅
- 跨平台（無路徑硬編碼 / 無新依賴）：✅
- Fix 2/3 失敗收縮（CLAUDE.md §二 #6）：✅（generic detail + server log 完整 stack）
- 不擴大範圍（未動 QC-S2-04 / SQL migration / 業務邏輯 / live boundary / strategy toml）：✅
- 文件大小：commands.rs 1343→1337（≤1500）；mod.rs 1109→1125（≤1500）

## 待確認 / 跨平台風險

1. Fix 1 行為改變：以前每 cycle ≥1 row，現可能 0 row → MIT dashboard 若用 row count 當 health signal 需通知
2. Fix 2/3 detail shape：原 string `"IPC error: ..."`，現 dict `{"reason": "ipc_error"}` → 前端若有 string match 會壞
3. Fix 4 `super::is_legacy_close_tag` 路徑驗證：cargo test 全綠

## 接力

E2 review → E4 regression（Linux production cargo test 復驗）→ PM Sign-off + commit + push。
建議 commit 拆 4 bullet 引 audit ID（MIT-S2-6 / E3-S2-P2-1 / E3-S2-P2-2 / PA-DRY-1）。

報告檔：`srv/.claude_reports/20260502_143228_e1_p2_wave_batch.md`
