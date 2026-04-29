# E1 — HELPERS-CLOSE-TAGS-SPLIT helpers.rs §九 file split

**Date**: 2026-04-29
**Author**: E1
**Predecessor**: W1-T1 (`2026-04-29--w1_t1_rust_schema_exit_reason.md`)
**完整 claude_report**: `srv/.claude_reports/20260429_201510_e1_helpers_close_tags_split.md`

---

## 任務摘要

W1-T1 加 +228 LOC 至 `helpers.rs` 後達 1639 LOC，違反 CLAUDE.md §九 1200 硬上限 + 「pre-existing baseline + 5 LOC」例外條款（1416 LOC 上限）。本任務把 W1-T1 新加的 `build_close_tags` helper + 4 unit tests 拆至 sibling `helpers_close_tags.rs`，**純 file split，0 logic change**，使 helpers.rs 回歸 baseline 1411 LOC，§九 完全合規。

## 範圍與成果

| 子項 | 檔 / 動作 | 結果 |
|---|---|---|
| (1) 新檔 `helpers_close_tags.rs` | 277 LOC：module 雙語 docstring（split rationale + W1-T1 範圍 + PA 指針）+ `pub(crate) fn build_close_tags` 完整搬遷 + `#[cfg(test)] mod tests` 4 個 unit tests | ✅ |
| (2) 修改 `helpers.rs` | 刪除 `build_close_tags` 函數本體（line 47-155）+ 上方 V033 雙語 docstring + 4 unit tests（V033 區頭 comment + 4 tests）| ✅ 1639 → **1411 LOC** = pre-existing baseline |
| (3) 修改 `mod.rs` | (a) 加 `mod helpers_close_tags;` (b) 把 `pub(crate) use helpers::build_close_tags;` 改 `pub(crate) use helpers_close_tags::build_close_tags;` (c) 加 5 行雙語 split-rationale comment | ✅ +10 LOC（160 → 171）|
| (4) cargo build + lib test 綠 | trade-core SSH bridge：`git apply` patch + `cargo build --release` + `cargo test --release --lib` | ✅ build OK + **2369 passed / 0 failed**（== W1-T1 baseline）|
| (5) §九 合規驗證 | `wc -l` 三檔 + 跨平台路徑 grep | ✅ helpers.rs 1411（baseline）+ helpers_close_tags.rs 277（< 800 warn）+ mod.rs 171；0 hardcoded path |

## 邊界自查

- ✅ 0 logic change — `build_close_tags` 函數體 byte-for-byte 搬遷，4 unit tests 完全保留
- ✅ 未動 16 個 W1-T2 emit point comment「`helpers::build_close_tags(...)`」(W1-T2 範圍；caller 路徑經 `crate::tick_pipeline::on_tick::build_close_tags` re-export 不破)
- ✅ 未動 helpers.rs 其他 helpers（`build_risk_close_tag` / `is_partial_reduce_tag` / `strip_phys_lock_prefix` / `log_phys_lock_through_combine_layer` / `compute_edge_estimates_file_age_secs` / `emit_shadow_exit_observation`）
- ✅ 0 觸碰 §四 live 5 hardguard
- ✅ 0 觸碰 risk_config / strategy params / Python / GUI / healthcheck
- ✅ 跨平台：grep `(/home/ncyu|/Users/[^/]+)` clean
- ✅ 雙語注釋全鏈（mod.rs 5 行 split-rationale 中英對照 + helpers_close_tags.rs module-level 雙語 docstring 50+ 行 + 函數 doc + tests comment 全雙語）

## §九 governance flag 解決

W1-T1 報告 §六 governance flag「helpers.rs 1639 違反 §九 baseline+5」已由本 split 解決：
- helpers.rs **回歸 baseline 1411**（< 1416 上限，§九 例外條款不需 invoke）
- helpers_close_tags.rs 277 LOC（< 800 warn）
- 後續主會話 commit Phase 2 第二波時，**E2 不需 invoke「baseline + 5 LOC」例外條款**

## 後續派發（建議主會話）

完成本 split → 主會話 commit Phase 2 第二波（healthcheck [38] fix + W1-T1 + helpers split）→ 派 W1-T2 16 emit point。W1-T2 派發前置（W1-T1 報告 §後續派發）：實測 `paper_state.get_position(symbol).strategy` 在 close-all path 能否取到 entry strategy（PA §5.4 R-A3 點明的盲點）。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-29--helpers_close_tags_split.md`）
