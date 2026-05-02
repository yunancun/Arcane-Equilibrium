---
name: 2026-05-02 codex 4-day audit chain
description: CC 4-day cold audit of 162 codex/operator commits (2026-04-28→05-01); P1-1 retrofit chain E1×3 / E2×3 / E4×3 closed; .codex/ governance set to option (a)
type: project
originSessionId: 258c0cfb-ca18-478e-9bc6-9bc900726628
---
**背景**：4 月 28 → 5 月 1 主 CC 缺席（限額），codex / operator 自主提交 162 commit / 581 檔 / +64k LOC（22 Co-Authored-By Claude，139 非 Claude）。5 月 2 主 CC 接手 cold audit。

**Audit findings**（commit `e858ae2` 收 step-1）：
- **P1-1 完成**（commit `e858ae2` r1+r2 + `6cb1c3b` r3）：5 SQL migration（V028/V030/V031/V032/V034）retrofit CLAUDE.md §七 Guard A/B + V031 view shape-guard。Chain = E1×3 → E2×3 → E4×3，9 輪 sub-agent 派發
- **P1-2 完成**：`test_rc_002_*` grep target 從 `loop_handlers.rs` 改 `status_report.rs`（c6ec664 file split 後 stale）
- **P2-1 完成**：`.coverage` `.gitignore` + `git rm --cached`
- **P2-4 完成**：`.codex/` 治理選 option (a) — 純 codex session 提示鏡像，不擁有治理權，衝突以 `.claude/agents/` + CLAUDE.md 為準。CLAUDE.md §十二 補述
- **P2-2/P2-3 + P3-1/2/3 deferred**：worktree merge spot check / single-commit 13.6k LOC 警示 / `is_legacy_close_tag` dedup / strategy params QC retro / TODO churn

**關鍵 lesson**（值得寫入 docs/lessons.md）：
1. **Codex 提交 governance 紅線會被踩**：CLAUDE.md §七 V023 silent-noop postmortem 後設立的 Guard A/B 強制規則，5/7 新 migration 違反；E2 對單個 13.6k LOC commit 審查近乎不可能 — 後續若 codex 繼續大量提交，須在 §七 加「單 commit 上限」規則
2. **CREATE OR REPLACE VIEW 不是 idempotent**：V031 fix 過程才發現 PG `CREATE OR REPLACE VIEW` 禁止 drop columns；任何 view 被後續 migration append cols 後，前面 migration 重跑會 FAIL。Pattern fix = view 用 DO/EXECUTE shape-guard（v_v031_cols subset of existing → NOTICE skip）
3. **Mac 無 PG 驗 migration 是 blind spot**：本機 cargo migrations_test 在無 `OPENCLAW_TEST_PG` 自動 skip；只能驗 wiring，不能驗 SQL execute。所有 migration retrofit 必須 E4 在 Linux production state 真實跑兩次才能簽 idempotent
4. **Linux 端沒 trading_ai_test 分離 DB**：`OPENCLAW_TEST_PG_DESTRUCTIVE=1` 跑 cargo `fresh_db_applies_all_migrations_end_to_end` 會 reset production；目前 workaround = skip Step 5，靠 Step 2/3/4/6/7 對 production trading_ai 跑 idempotent + read-only safe；長期應建 trading_ai_test
5. **多輪 sub-agent chain 真的會 catch bug**：E2 round 1 沒 catch 的 V031 view idempotency issue 被 E4 round 2 對真實 PG 抓出 — 印證 CLAUDE.md §八「Verify-Before-Done」+ multi-role adversarial review 不可跳

**Step 2 cold audit 待派**（user 簽 step-1 完成後）：PA + MIT + QC + E3 並行 cold review 過去 4 天非 docs commit，不依賴 commit message 自述。
