# E1 Round 3 — V031 view-shape guard fix（AUDIT-2026-05-02-P1-1）

## 1. 任務摘要

E4 round 2 在 production DB（commit `e858ae2`，V034-applied state）對 V031 跑 idempotency 撞 `cannot drop columns from view`。原因：V031 round 1 / 2 自報「CREATE OR REPLACE VIEW idempotent / 不需 guard」是錯誤推論 — Postgres 規格上 CREATE OR REPLACE VIEW 不允許 DROP columns；V034 為 `learning.mlde_edge_training_rows` 加 18 個 `scanner_market_*` 欄成 53 欄，V031 第二次跑試圖窄化 → PG 拒絕。

Round 3 修法（E4 推薦 Option B）：對 V031 的 view 創建包一層 view-shape guard，用 DO/EXECUTE block 條件化 CREATE OR REPLACE。三路徑：fresh-install / view-already-extended（skip） / view-missing-baseline（RAISE）。

## 2. 修改清單

| path | 動作 | 行數 | 說明 |
|---|---|---|---|
| `srv/sql/migrations/V031__ml_dream_edge_unblock.sql` | 修改 | +173 / -8 | DO/EXECUTE 包覆 view body + view-shape guard 三路徑邏輯，更新 retrofit 註解（中英對照）撤回 round 1/2 自報 |
| `srv/sql/migrations/tests/test_v028_v034_guards.sql` | 修改 | +192 / -8 | 新增 V031/View-fresh / View-extended / View-drift 3 cases；同步更新 Coverage 註解 |

未動 V028 / V030 / V032 / V034 / 既有 V031 mlde_shadow_recommendations Guard A / view body SQL 業務邏輯。

## 3. 治理對照

| 規則 | 狀態 |
|---|---|
| CLAUDE.md §七 規則 4 — idempotency 第二跑不 RAISE | 修補 ✅ |
| CLAUDE.md §七 規則 1 — Guard A 強制 | 維持 + sibling view-shape guard ✅ |
| CLAUDE.md §七 雙語注釋 | ✅ |
| CLAUDE.md §七 跨平台 | ✅（0 硬編碼路徑） |
| CLAUDE.md §二 #6 失敗收縮 / #8 可解釋 | ✅ |
| 不擴大範圍 | ✅ |

## 4. 驗證 checklist

- [x] **本機 V031 重跑 ≥3 次** — Mac PG 16.13 + V034-applied state，view 維持 53 欄，零 ERROR
- [x] **NOTICE 訊息可見** — `V031 view-shape guard: learning.mlde_edge_training_rows already contains all V031 baseline cols (likely extended by V034+); skipping CREATE OR REPLACE VIEW to avoid 'cannot drop columns from view' error. View body is unchanged.`
- [x] **test fixture 21/21 PASS** — 含 3 個新增 V031/View-* tests
- [x] **`cargo test -p openclaw_engine --test migrations_test --release`** — 5/5 pass
- [x] **`git diff --check`** — 0 whitespace issue
- [x] **`git status --short`** — 只見 V031 + test fixture 兩檔
- [x] **未動 V028 / V030 / V032 / V034**
- [x] **未動 view body 業務邏輯（SELECT / WHERE / JOIN / CTE / metadata 全 verbatim）**

## 5. 不確定 / 跨平台風險

1. 本機 PG 16.13 缺 TimescaleDB；V005/V010/V023/V026 部分 DDL 失敗，不影響 V031/V034 路徑驗證；E4 round 3 應在 Linux production DB（有 TimescaleDB）confirm。
2. NOTICE message 用 implicit string concat（相鄰字串 literal），PG 14+ 行為一致。
3. v_v031_cols 34-col list 與 V034 既有 guard 100% 同序同名；任一未來 migration 對 view 改 leading col 都需同時更新兩處。

## 6. Operator 下一步

- E2 審查 V031 view body verbatim 等價性 + v_v031_cols 與 V034 一致性
- E4 round 3 在 Linux production DB（commit `e858ae2`，V034-applied state）對 V031 跑 idempotency check：
  ```
  ssh trade-core "cd ~/BybitOpenClaw/srv && psql -U trading_admin -d trading_ai -v ON_ERROR_STOP=1 -f sql/migrations/V031__ml_dream_edge_unblock.sql 2>&1 | grep -E 'NOTICE|ERROR'"
  ```
  期望：見 NOTICE-skip 訊息，零 ERROR，view 53 欄不變。
- PM 統一 commit + push（E1 不自行 commit；CLAUDE.md §七 鏈 E1→E2→E4→PM）。

## 7. Lessons (建議寫入 docs/lessons.md)

**Pattern**：retrofit guard 寫 disclaimer 時忽略 production runtime state。
**Scenario**：V031 round 1/2 自報「CREATE OR REPLACE VIEW idempotent / 不需 guard」 — 推論只在 fresh-install state 成立，沒考慮 V034 已對同一 view append 18 cols 的 production state。
**Prevention rule**：post-V023 retrofit / 任何 idempotency disclaimer，必須對齊 **production runtime DB state** 而非僅 fresh install 假設。E2 審查 disclaimer 時要 push back「在 production state 也成立嗎」。
**Related**：`sql/migrations/V031__ml_dream_edge_unblock.sql`、`sql/migrations/V034__mlde_scanner_context_columns.sql`（V034 round-2 retrofit 已正確處理，V031 round 1/2 漏掉）。
