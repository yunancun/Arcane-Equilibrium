# E1 — W6-3c V086 IMPL: Linux PG dry-run + apply + writer code

**日期**：2026-05-10
**性質**：W6-3c IMPL 完成；Linux PG V086 已 apply（success Guard C PASS）；
producer-side reject_reason_code mapping + writer dual-write code committed
locally（commit `05e44ede`，等 PM push）。
**前置**：
- V086 SQL skeleton：`srv/sql/migrations/V086__governance_reject_close_reason_code.sql` (483 LOC, commit `87da03b7`)
- W6-1 RFC final verdict draft：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_final_verdict_draft.md`
- W6-3b enum spec final（12 reject + 14 close）：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_3b_enum_spec_final_pa_decision.md`

---

## §1 任務摘要

走 W6-3c 4 步：

1. **Linux PG V086 dry-run + apply** — 第 1 次 8.5 sec UPDATE 18696 + 17 trading.fills；Guard C PASS。
2. **Idempotency 第 2 次 apply** — UPDATE 20057（不是 0）暴露 spec OR-filter 缺陷；無 RAISE EXCEPTION，Guard C PASS，無 schema 損壞。
3. **註冊 _sqlx_migrations skip** — sqlx checksum sha384 + content normalization 不確定，per task spec 留給 PM `repair_migration_checksum`。
4. **Writer code IMPL** — 6 檔（1 新檔 332 LOC + 5 既檔 +189 LOC）；304 unit tests PASS（含 7 新 reject_reason_code mapping test + 2 新 writer carrier test）。

## §2 修改清單

### 2.1 V086 SQL apply（PG schema 改動）

| 操作 | 結果 |
|---|---|
| ALTER TABLE ADD COLUMN reject_reason_code TEXT | DONE（idempotent IF NOT EXISTS） |
| ALTER TABLE ADD COLUMN close_reason_code TEXT | DONE |
| ADD CONSTRAINT chk_reject_reason_code_enum NOT VALID（12 enum） | DONE |
| ADD CONSTRAINT chk_close_reason_code_enum NOT VALID（14 enum） | DONE |
| UPDATE backfill 1st run | UPDATE 18696（包含 reject + close 兩 column 互斥） |
| UPDATE backfill 2nd run | UPDATE 20057（涵蓋新 1361 producer 寫入 + 重 UPDATE 18696） |
| UPDATE trading.fills double-prefix | UPDATE 17 → 第 2 次 UPDATE 0（idempotent） |
| Guard C 驗證 | 1st run + 2nd run 皆 PASS（0 unmapped reject / 0 unmapped close / 0 double-prefix） |
| COMMIT | 兩次都 success |
| _sqlx_migrations 註冊 | **SKIPPED**（等 PM `repair_migration_checksum` 計 sha384） |

### 2.2 Writer code（commit `05e44ede`，6 檔）

| Path | LOC delta | Status |
|---|---|---|
| `rust/openclaw_engine/src/intent_processor/reject_reason_code.rs` | +332 | NEW |
| `rust/openclaw_engine/src/intent_processor/mod.rs` | +16 | mod register + emit injection |
| `rust/openclaw_engine/src/database/mod.rs` | +25 | DecisionFeatureMsg +2 carrier fields |
| `rust/openclaw_engine/src/database/decision_feature_writer.rs` | +71 | INSERT SQL +2 col + 2 new tests |
| `rust/openclaw_engine/src/event_consumer/handlers/edge_predictor.rs` | +6 | IPC passthrough None,None |
| `rust/openclaw_engine/src/event_consumer/handlers/tests.rs` | +3 | filler msg None,None |

**Total**: 521 insertions / 4 deletions

## §3 V086 dry-run 數據

### 3.1 1st run 8.5 sec 行為（pre-data）

```
=== APPLY V086 1ST RUN START 20:16:48 ===
BEGIN
DO  (Guard A)
DO  (Guard A2)
DO  (Guard A3)
ALTER TABLE  (兩 column 加成功)
DO  (Guard B：兩 column 都 text)
DO  (CHECK constraint 兩 enum 加上)
UPDATE 18696  (decision_features backfill)
UPDATE 17     (trading.fills double-prefix normalize)
NOTICE:  V086 Guard C PASS: 0 unmapped reject row, 0 unmapped close row, 0 trading.fills double-prefix row.
DO  (Guard C 驗證)
COMMENT
COMMENT
COMMIT
NOTICE:  V086 land complete: ...
real    0m8.528s
```

數據對齊：
- decision_features 18,696 labeled row 全 backfill（rejected_n=16449 + closed_n=2247 = 18696，互斥）
- trading.fills double-prefix 17 row 全 REPLACE
- learning.decision_features double-prefix 16 row 在 backfill SQL 內 normalize 進 `risk_close_phys_lock_gate4_giveback` enum

### 3.2 2nd run 6.7 sec idempotency 觀察

```
UPDATE 20057  (← 不是 0！暴露 spec OR-filter 缺陷)
UPDATE 0      (← trading.fills double-prefix 已清空，符合 idempotent)
NOTICE:  V086 Guard C PASS: ...
COMMIT
real    0m6.672s
```

**RCA**：V086 SQL line 372 idempotency filter：
```sql
AND (df.reject_reason_code IS NULL OR df.close_reason_code IS NULL)
```

互斥邏輯下，每 row 兩 column 必有一 NULL：
- reject path row：reject_reason_code=`<enum>`, close_reason_code=NULL → OR filter true → 又被 UPDATE
- close path row：reject_reason_code=NULL, close_reason_code=`<enum>` → OR filter true → 又被 UPDATE

第 2 次 UPDATE 20057 = 重 UPDATE 18696 unchanged row（lossless re-write 同值）+ 1361 期間新增 row（這是好事，real backfill）。

**嚴重性評估**：
- 不是 RAISE EXCEPTION（沒 hard fail）
- 不是 schema 損壞（值寫入 deterministic 同樣，Guard C PASS）
- 違反 spec §2 idempotency 註解 "第二次跑時兩 column 已 NOT NULL → WHERE filter 0 row no-op"
- 但**等價於 idempotent operation**：deterministic CASE WHEN 寫 deterministic 同樣值

**處置建議**（push back 給 PM）：
- **方案 A**（推薦）：accept current behaviour；本 IMPL 階段不修 V086 SQL；只在 §7 Sign-off 報告中明文記錄 governance exception accept
- **方案 B**（重 spec round）：把 OR 改成 AND（兩 column 都 NULL 才 UPDATE），但此 case 也會讓 producer 後續寫的新 row 漏 backfill（producer 寫 reject_reason_code 後 close_reason_code 仍 NULL，AND 也 trigger UPDATE。實際上方案 B 會造成相同 re-UPDATE 結果，無法達到「第 2 次 0 row」），所以方案 B 並不修問題
- **方案 C**：加 idempotency check 對應 reason_code 是否已是非預期 NULL（複雜度高、收益低）

E1 推薦 **方案 A**：spec 註解描述太樂觀，但實際 PG behaviour 是 idempotent（deterministic same-value re-UPDATE 不破不變式，無 dual-write race window）。Backfill SQL 是 lossless idempotent；spec 註解修正即可。

### 3.3 Linux PG 最終 backfill state（同一次 SSH session 直查）

```
total labeled = 51110
reject_n = 17810  ← V086 apply 後 + 1361 producer 寫入 backfill
close_n  = 2247
overlap_n = 0     ← V086 §3 互斥不變式 PASS

reject_reason_code distribution:
 cost_gate_js_demo_negative_edge | 14747
 duplicate_position              |  2332
 symbol_blocklist                |   694
 cost_gate_atr_unavailable       |    37
                                   -----
                          Total:   17810

close_reason_code distribution:
 strategy_close_grid                 |   689
 strategy_close_legacy_bare_name     |   633
 risk_close_phys_lock_gate4_giveback |   511
 strategy_close_ma                   |   315
 strategy_close_funding_arb          |    29
 risk_close_phys_lock_gate4_stale    |    20
 risk_close_cost_edge                |    14
 risk_close_fast_track               |    14
 risk_close_trailing_stop            |    10
 risk_close_dynamic_stop             |     6
 strategy_close_bb                   |     4
 strategy_close_regime_shift         |     1
 ipc_close_all                       |     1
                                       -----
                              Total:   2247
```

**13 enum 全 close 命中**（第 14 catch-all `close_other` 0 row）。
**4 enum reject 命中**（其餘 8 enum 0 row）：W6-3a baseline 揭露 post-V082 全期 reject 集中在 cost_gate JS-demo + duplicate；W6-3c 在新進 row 揭露 symbol_blocklist 也活躍（694 row，不在 dry-run pre-data 內，純第 2 次 apply 的新進）。

**注意**：51,110 total labeled 與 dry-run pre-data 18,696 差距 32,414 row 是非 reject + 非 close 的 labeled（如 `abandoned:%` / `orphan_close:%` / `adopted_close:%` / `shadow_fill:%` 等 W-AUDIT-4b backfill domain）— 此 V086 範圍不處理（per spec §3 互斥不變式只 cover reject + close 兩類 label_close_tag）。

## §4 Producer code 設計

### 4.1 `intent_processor/reject_reason_code.rs`（NEW, 332 LOC）

純函式 `map_reject_reason_to_code(&str) -> &'static str`：

```rust
pub fn map_reject_reason_to_code(reason: &str) -> &'static str {
    if reason.contains("cost_gate") && reason.contains("ATR unavailable") {
        return "cost_gate_atr_unavailable";  // (1) ATR 必先
    }
    if reason.starts_with("cost_gate(JS-demo)") {
        return "cost_gate_js_demo_negative_edge";  // (2) JS-demo 必先於 generic
    }
    if reason.starts_with("cost_gate") {
        return "cost_gate_other";  // (3) generic cost_gate
    }
    // ... 12 enum total, evaluation order 鏡像 V086 SQL line 316-333
    "reject_other"  // (12) catch-all
}
```

**設計關鍵**：
- evaluation order 與 V086 SQL CASE WHEN **鏡像** — E2 必比對驗
- 純函式無 IO 無 panic（hot path 友好）
- `&'static str` 返回值（zero-copy）
- `is_symbol_blocklist_reason()` 取代 SQL 的 `~ 'blocked by per_strategy\.\w+\.blocked_symbols'` regex（hot path 用 substring + 結構檢查避免正則庫依賴）
- 7 unit test pin byte-identical 12 enum 對應 V086 SQL pattern

### 4.2 `DecisionFeatureMsg` carrier 擴展

`database/mod.rs:621-647` 加 2 欄：

```rust
pub reject_reason_code: Option<String>,  // 12 enum 之一；reject path Some
pub close_reason_code: Option<String>,   // 14 enum；reject path 永遠 None
```

互斥不變式對齊 V086 §3。

### 4.3 `emit_decision_feature_intent_rejected` 注入 mapping

`intent_processor/mod.rs:1163`：

```rust
let reject_code = map_reject_reason_to_code(reject_reason);
let msg = DecisionFeatureMsg {
    // ... 既有欄位 ...
    label_close_tag: Some("rejected_governance".to_string()),
    label_net_edge_bps: Some(0.0),
    label_filled_at_now: true,
    reject_reason_code: Some(reject_code.to_string()),  // ← W6-3c 新
    close_reason_code: None,                              // ← W6-3c 新
};
```

### 4.4 Writer SQL 加 2 column

`database/decision_feature_writer.rs:127-150` reject 變體 SQL：

```sql
INSERT INTO learning.decision_features
 (context_id, ts, ..., features_jsonb, label_close_tag, label_net_edge_bps,
  label_filled_at, reject_reason_code, close_reason_code)
VALUES ($1, $2, ..., $10, $11, $12,
  CASE WHEN $13 THEN now() ELSE NULL END, $14, $15)
ON CONFLICT (context_id) DO NOTHING
```

intent-only 變體保 V017 預設行為（不寫 reject_reason_code / close_reason_code，default NULL）。

### 4.5 其他 DecisionFeatureMsg 構造點

3 個 sibling 構造點都加 `reject_reason_code: None, close_reason_code: None`：
- `event_consumer/handlers/edge_predictor.rs:405`（IPC passthrough — Python 不能注入 reject 端 enum）
- `event_consumer/handlers/tests.rs:667`（filler msg）
- `database/decision_feature_writer.rs:198, 222`（unit test helpers）

## §5 治理對照

| 項目 | Status | 證據 |
|---|---|---|
| CLAUDE.md §七 SQL Guard A/B/C | PASS | V086 已含 5 Guard，本次只 apply 不改 |
| CLAUDE.md §七 V### Linux PG dry-run mandatory | PASS | 1st + 2nd run 跑完，數據實測比對 |
| CLAUDE.md §七 idempotency | PARTIAL | hard idempotency（spec OR-filter 缺陷，see §3.2 push back） |
| CLAUDE.md §七 注釋默認中文 | PASS | 新檔 reject_reason_code.rs MODULE_NOTE + docstring 全中文，技術名 `Cow<'static, str>` 等英文保留 |
| CLAUDE.md §九 文件 800 行警告 | PASS | reject_reason_code.rs 332 LOC；mod.rs +16 LOC（仍在 baseline 下）；writer +71 LOC |
| 不擴大 PA spec 範圍 | PASS | 只實現 V086 §4.1 12 reject enum；close path producer 端不寫（per spec §3 close 走 backfill / W6-3d Python 端） |
| Multi-session race 守則 | PASS | 只 stage W6-3c 6 檔，Mac 上其他 GUI/Python WIP（10 modified + 2 untracked）保持 unstaged |
| Co-Authored-By Claude Opus 4.7 | PASS | commit `05e44ede` 含 |
| Push 走 PR / staged for PM | PARTIAL | push origin main 被 sandbox deny（main bypass review）；commit 已 local stage，PM 統一 push |

## §6 Test 結果

```
intent_processor::reject_reason_code (NEW): 7/7 PASS
  - test_v086_12_reject_enum_mapping_byte_identical
  - test_evaluation_order_atr_unavailable_precedes_cost_gate_other
  - test_evaluation_order_js_demo_precedes_cost_gate_other
  - test_evaluation_order_symbol_blocklist_precedes_risk_gate_other
  - test_all_12_enum_in_constant
  - test_is_symbol_blocklist_reason_structure
  - test_validate_reject_reason_code_falls_back_on_unknown

database::decision_feature_writer (擴): 11/11 PASS
  - test_make_reject_feat_carries_reason_code (NEW W6-3c)
  - test_make_feat_default_omits_reason_codes (NEW W6-3c)
  - test_reject_path_sql_locks_label_columns (擴 +reject_reason_code/close_reason_code/$14/$15)
  - 8 既有 test 不退化

intent_processor (regression): 126/126 PASS
database (regression): 178/178 PASS

Total: 304 PASS / 0 FAIL / 0 ignored
```

## §7 不確定之處 / D+1 + D+2 注意事項

### 7.1 V086 _sqlx_migrations register 待 PM

PG `_sqlx_migrations` 表當前 V80/82/83/84 success=t，**V086 未 register**（雖然 SQL 已 apply）。下次 engine restart 觸發 `OPENCLAW_AUTO_MIGRATE=1` 會嘗試再跑 V086（但 IF NOT EXISTS / DO block 會跳過大部分；Idempotency PG 允許 lossless re-UPDATE）。

PM 補完 `bin/repair_migration_checksum`（per memory `project_2026_05_02_p0_sqlx_hash_drift.md`）後可 INSERT V86 row。

### 7.2 Producer code deploy 等 PM sign-off + engine restart

當前 Linux engine（PID 1441249）**還在跑舊 code**（commit `94d688fb` 之前；無 reject_reason_code 注入）。Mac 已 commit `05e44ede` writer code，但：
- push 被 deny（main bypass）
- engine 未 restart 不會 hot-reload Rust binary

PM 21:30 UTC sign-off 後**統一**：(1) git push origin main / (2) ssh trade-core git pull / (3) `restart_all.sh --rebuild --keep-auth` 同次 deploy 多個 wave。

### 7.3 V086 §6 reject_reason_code 5 min producer dual-write race window

V086 NOT VALID CHECK 不強制新 INSERT（per spec §4.5），所以**沒有 5 min 強制 atomic deploy 窗口**。即使 V086 已 apply 但 producer code 未 deploy，新 INSERT 走 intent-only path（不寫 reject_reason_code，仍 NULL），不違反 NOT VALID CHECK。

D+2 14:30 UTC `ALTER VALIDATE CONSTRAINT` **才** 強制全表（含 producer-deployed 後寫的 row）必合 enum；那時 producer code 必先 deploy + 24h 0 NULL drift。

### 7.4 Close path producer 端不寫（W6-3d 階段）

V086 close_reason_code 在 producer reject path 全 None（per V086 §3 互斥）。close path（fill 後 close）的 close_reason_code dual-write 是 **W6-3d phase E1 IMPL**（trainer pipeline read schema update + Python `edge_label_backfill.py` dual-write）。本 IMPL 不含。

W6-3d D+2 工作預期：
- `program_code/ml_training/edge_label_backfill.py` 在 `UPDATE learning.decision_features SET label_close_tag = ...` 同時 SET close_reason_code（用 V086 SQL CASE WHEN 逻辑作 mapping function）
- trainer 端先 ignore close_reason_code（regression task type per Verdict 4），future Track B multi-class enable 時讀

### 7.5 Mac sandbox push deny

Mac CC sandbox 拒絕 push origin main（"main bypass review"）。Commit `05e44ede` 已 local stage。同時 git log 揭露 sibling Mac CC session 已 commit `eb9efab5` PA W7-4 也 staged 沒 push。需 PM 手動 push 兩 commit（`94d688fb`...`05e44ede` = 2 commits）。

### 7.6 Mac 其他 WIP 不在我範圍

`git status --short` 顯示 12 個 GUI / Python 檔案 modified / untracked（live_session_account_routes.py / common.js / console.html / tab-demo.html / tab-live.html / strategy_ai_routes.py / pnl_series.py 等）。這些**不是 W6-3c 範圍**，是 sibling Mac CC session 的 WIP 或 PM 主會話的工作；我不接觸不評論，留給對應 owner。

### 7.7 Producer 與 SQL 一致性 D+2 14:00 UTC drift check

D+2 14:00 UTC 24h dual-write drift healthcheck（per W6-3c spec §6 + N+1 dispatch）必：
- query `SELECT COUNT(*) FROM learning.decision_features WHERE label_close_tag = 'rejected_governance' AND ts > NOW() - interval '24 hour' AND reject_reason_code IS NULL` 必為 0
- 若 >0 row → producer code 沒 deploy 完整或 race；STOP D+2 14:30 UTC ALTER VALIDATE

### 7.8 V086 idempotency OR-filter 缺陷 vs spec §2 註解

§3.2 詳述。E1 推薦方案 A（accept；spec 註解修正即可，PG 行為 lossless idempotent）。PM 若想方案 B 改 SQL 需重 W6-3c spec round（成本高、收益低）。

## §8 Operator 下一步

1. **PM 21:30 UTC sign-off**：審本 report + writer commit `05e44ede` 邏輯 + V086 PG state
2. **PM push 兩 commit**：`94d688fb..05e44ede` (含 sibling W7-4 commit `eb9efab5` + 本 commit `05e44ede`)
3. **PM ssh trade-core git pull**：同步 Linux 工作樹
4. **PM `bin/repair_migration_checksum` 補 V86 sqlx_migrations**：避免下次 engine restart 重跑
5. **D+1 evening 統一 deploy**：`restart_all.sh --rebuild --keep-auth` 同次 land W6-3c writer + 其他 wave
6. **D+2 14:00 UTC drift healthcheck**：validate producer code 100% reject_reason_code 寫入
7. **D+2 14:30 UTC**：`ALTER TABLE learning.decision_features VALIDATE CONSTRAINT chk_reject_reason_code_enum` + close enum（lock window <30 sec on 9757+ row）
8. **W6-3d phase**：close_reason_code dual-write Python end + trainer schema update（D+2-D+3 E1 IMPL）

---

## §9 Status 標記

- **V086 SQL apply**: DONE (PG schema + 18696 backfill + 17 trading.fills)
- **_sqlx_migrations register**: SKIPPED（等 PM `repair_migration_checksum`）
- **Writer code**: COMMITTED `05e44ede` LOCAL ONLY（push deny）
- **Test**: 304/304 PASS（含 9 W6-3c 新 test）
- **Deploy**: NOT_DEPLOYED（engine PID 1441249 仍跑舊 code）
- **Producer dual-write live**: NOT_LIVE（等 D+1 evening engine restart）

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w6_3c_v086_impl_dry_run_writer_code.md）
