---
name: LinUCB shadow compare 保留決策
description: Phase 4 子任務 4-06 遺留 Python library 的保留理由與條件性激活觸發點；2026-04-23 歸檔審核後決定保留不刪
type: project
originSessionId: 6ebc2016-7557-4ddd-a03f-8418227b1456
---
`program_code/ml_training/linucb_shadow_compare.py` (~300 行 + 配套 `test_linucb_shadow_compare.py` ~63 行) 於 2026-04-23 Phase 4 歸檔 audit 後**保留**不刪。

**Why:** Phase 4 子任務 4-06（LinUCB live warm-start 首次 v1→v2 arm 遷移）仍在 TODO.md 列為「條件性激活」— 待 arm 策略真正啟動時再執行。該檔為純 `decide(champion_rewards, challenger_rewards, config) → ShadowCompareResult` 決策 library（promote / keep_champion / insufficient_data 三分支），無 CLI / 無 DB query / 無 side effect，zero maintenance cost。若 Phase 5 edge 重評（P0-3，最早 2026-05-07）後 arm migration 重啟，這 300 行已 debugged + 3 tests 驗證的決策邏輯直接可用，刪了將來從 git history 復原比保留更麻煩。

**How to apply:** 下次 audit 見到此檔不要再提議刪除；只有當以下條件之一滿足時才可重啟刪除討論：
1. Rust engine 實裝完整 LinUCB warm-start migration（含 auto-rollback），Python library 徹底被取代
2. 4-06 被正式降級為「永遠不做」（TODO.md 移除該條目）
3. arm 策略架構方向改變（如改用 Thompson Sampling 等非 LinUCB 方法）

同次 audit 中 `helper_scripts/phase4/backfill_directive_outcomes.py` 已刪（2026-04-23 commit，Rust `outcome_backfiller.rs` 已取代且於 `5e2981d` 修好 bug 成為權威）；兩檔命運不同是因為 Rust 取代狀態差異：backfill 已實裝、linucb warm-start 未實裝。
