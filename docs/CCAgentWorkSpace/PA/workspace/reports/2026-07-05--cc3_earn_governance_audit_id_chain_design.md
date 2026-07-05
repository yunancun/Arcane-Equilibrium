# CC-3 / OOS-1 — Earn governance_audit_log id chain 技術設計

STATUS: DESIGN-ONLY / DORMANT pending Wave D/E unfreeze
Author: PA · Date: 2026-07-05 · Scope: 兌現 `earn_router.rs:376` 的 PA-DRIFT-6 sentinel（audit-lineage 缺口，非 fail-open）
Risk grade: 中（改 earn dispatch 失敗語意 + 引入 audit DB 寫入到 Bybit call 之前；不觸 live 五 gate / 不改 API schema）。**§7 已由 operator 拍板 2026-07-05 = (b)**：帶一支 idempotent event_type CHECK V-migration（26→28 value，走 Linux PG double-apply dry-run）。

---

## 0. 一句話結論

- **架構問題結論 = (B)**：`learning.governance_audit_log` 是 **multi-producer append-only event log**，允許多 module 各自 INSERT，**不是**單一 audit-writer 權威。證據：Python 端已有 ≥3 個獨立 INSERT 點（`handoff_audit.py:219`、`governance_hub_live_candidate_review.py:694/784/848`），各寫不同 `event_type`；Rust engine 端**零** INSERT。因此 `EarnMovementWriter` 對同 schema 的 `governance_audit_log` 做 raw INSERT **不違反 root principle 1**（單一寫入口是指**訂單/交易執行**寫入口，非 audit-log 寫入口）。
- **scope item (1) 最終形狀 = 「`EarnMovementWriter` 新增 `insert_governance_audit_log(...) -> RETURNING id`」**，複用它已持有的 engine main pool（`bootstrap.rs:1229` `EarnMovementWriter::new(pool.clone())`），與它對 sibling 表 `earn_movement_log` 的 raw INSERT 完全同範式。**不走 IPC、不新建 audit-writer 抽象。**
- **event_type 決策已 RESOLVED（operator 2026-07-05 = (b)，見 §7）**：加一支 idempotent V-migration 補 `earn_stake_approval` / `earn_redeem_approval`（26→28 value canonical CHECK），event_type 層一級可濾、徹底閉合 audit lineage。event_type 由 direction 決定 → helper fn（§7.2），非單一常量。

---

## 1. de-risk：最高風險架構問題的親證結論

### 1.1 halt_audit.rs「透過 IPC 傳給 audit writer」是什麼？

`halt_audit.rs:8/253` 的註釋（"透過 IPC 傳給 audit writer，本模塊本身不直連 PG —— engine 同 process 內無 audit pool handle"）描述的是 **halt-session 場景的歷史限制**：`halt_audit.rs` 本身是純檔案 forensic logger（`write_jsonl_line`），它自己確實沒有 PG pool handle，所以它把 governance_audit_log 那一 hop **外包給呼叫端 / Python-side**。

grep 全 Rust engine（`grep -rn "INSERT INTO ...governance_audit_log" rust/`）→ **0 個 Rust INSERT 命中**。唯一命中是 `earn_movement_writer.rs:425` 的 `lookup_governance_approval` 反查 SELECT。

真正的 governance_audit_log INSERT 權威全在 **Python control_api**：
- `replay/handoff_audit.py:219` — handoff attempt，`event_type='...handoff...'`
- `app/governance_hub_live_candidate_review.py:694/784/848` — live candidate review，`event_type='review_live_candidate'` 等
- 三處都是 **fire-and-forget append**（psycopg2 `cursor.execute`，**無 RETURNING**，不取回 id）。

### 1.2 Rust 的 `AuditWriter`（persistence.rs:125）是不同表面

`persistence.rs::AuditWriter` + `event_consumer/bootstrap.rs:1156` 是**本地 JSONL 檔案** audit writer（`{kind}_audit.jsonl`），**不是** PG `governance_audit_log`。別混淆。halt_audit 的 forensic log 也是 JSONL 檔。這兩條都是「檔案 audit」，與「PG governance_audit_log」是兩個獨立表面。

### 1.3 為什麼 earn 端可以（且應該）直接 raw INSERT，而 halt 端不行

決定性差異 = **pool handle 的可得性**。
- halt_audit 在 close-all loop 的 sync 熱路徑，該模塊刻意零依賴、不吃 PG pool（模塊獨立性最大化，`halt_audit.rs:200-206` 註釋自述）。
- **earn 端不同**：`EarnMovementWriter` **已經持有** engine main audit pool（`bootstrap.rs:1228-1229`，`wire_earn_capabilities(audit_pool)` → `EarnMovementWriter::new(pool.clone())`）。它已用這個 pool 對 `learning.earn_movement_log` 做 `insert_placeholder` / `write_failure`（含 `RETURNING movement_id`）。對同一個 `learning` schema 的姊妹表 `governance_audit_log` 做同樣的 raw INSERT + `RETURNING id`，是**零新基礎設施**的自然延伸。

→ 因此 (A) 「必須改走既有 audit-writer 權威而非新 raw INSERT」**不成立**。既有 audit-writer 權威（Python fire-and-forget）反而**無法回傳 id**（無 RETURNING），若硬走 Python 反而要新建一條 Rust→Python IPC round-trip 只為取一個 id，且把 earn critical path 綁死在 Python control_api 可用性上 —— 那才是壞設計。Rust-first（memory `feedback_new_code_rust_first`）+ 既有 pool + sibling 範式 = raw INSERT 是讀碼成本最低、依賴最少的正解。

---

## 2. Ground truth 引用表（PM 已核對，本設計直接採用）

| # | 事實 | 證據 file:line |
|---|---|---|
| GT-1 | governance_audit_log 表已存在（hypertable），**0 新 migration 建表** | `V035__governance_audit_log.sql`（CREATE TABLE + create_hypertable on `ts`）|
| GT-2 | event_type CHECK = 26-value canonical，**無 earn 值** | `V113:...ADD CONSTRAINT ...CHECK (event_type IN (...26 values...))`；base `V053`(14) + `V054`(lease 7) + `V098`(halt 3) + `V113`(pg_dump 2) |
| GT-3 | reconciliation cron **不讀** governance_approval_id 做過濾 | `cron/earn_reconciliation.rs` WHERE 只 key on `reconciliation_status='pending'`（`earn_movement_writer.rs:395-396`）；cron 的 reader trait 只 `compute_local_net_flow` / `update_past_24h_pending` / `count_consecutive_mismatch_days`，**從不投影 governance_approval_id** |
| GT-4 | 反查半段已建 | `earn_movement_writer.rs:418 lookup_governance_approval`（SELECT `WHERE g.id=$1`），test 斷言 `:648-657` |
| GT-5 | module doc 早已寫明預定鏈 | `earn_movement_writer.rs:48`「先寫 governance_audit_log 取 id 再注入 writer」 |
| GT-6 | :370 誤導註釋 —— **hash-fallback 從未存在於代碼** | `earn_router.rs:370`「採 string→hash i64 fallback」，但 `:376` 實際只是 `= 0` |
| GT-7 | writer 已持 engine main pool | `bootstrap.rs:1228-1229`；`earn_movement_writer.rs:139-147 EarnMovementWriter{pool}` |
| GT-8 | Python audit INSERT 是 fire-and-forget，無 RETURNING | `handoff_audit.py:219`（無 RETURNING）；`governance_hub_live_candidate_review.py` INSERT 無 RETURNING |
| GT-9 | `decided_by TEXT NOT NULL`（V035）—— audit INSERT 必給非空 | `V035` `decided_by TEXT NOT NULL` |
| GT-10 | earn 的 approval_id 是 String UUID（forensic），actor_id 是 operator role | `mod.rs:158-175 EarnIntentPayload{approval_id: String, actor_id: String}`；`earn_router.rs:313-319 intent_id` 組裝 |

---

## 3. scope item (1) — `insert_governance_audit_log` 精確設計

### 3.1 函數簽名（新增於 `earn_movement_writer.rs` `impl EarnMovementWriter`）

```rust
/// 先寫 learning.governance_audit_log 取 BIGSERIAL id，供 earn_movement_log
/// 的 governance_approval_id soft-ref 注入（兌現 PA-DRIFT-6 預定鏈，earn_movement_writer.rs:48）。
///
/// 為什麼 raw INSERT 而非走 Python audit writer：
///   - governance_audit_log 是 multi-producer append-only event log（B 型，非單一寫入權威）；
///   - 本 writer 已持 engine main pool（同 earn_movement_log 寫入 pool）；
///   - Python 端 INSERT 皆 fire-and-forget 無 RETURNING，無法回傳 id；走 IPC 只為取 id
///     會把 earn critical path 綁死於 control_api 可用性。
///
/// RETURNING id：governance_audit_log PK = (id BIGSERIAL, ts)，取 id 即可（ts 不需回傳）。
pub async fn insert_governance_audit_log(
    &self,
    event_type: &str,          // §7.2 決策(b)：earn 專用值 "earn_stake_approval"/"earn_redeem_approval"（需 §7.1 V-migration）
    decision_lease_id: &str,   // = earn lease_id 的 String（審計鏈 join key，見 §3.4）
    decided_by: &str,          // NOT NULL → 傳 actor_id（operator role），絕不空字串
    payload: &JsonValue,       // forensic：approval_id(UUID) / intent_id / direction / amount / engine_mode / api_scope
) -> Result<i64, EarnMovementError> {
    let row = sqlx::query(
        r#"
        INSERT INTO learning.governance_audit_log (
            event_type,
            decision_lease_id,
            decided_by,
            payload
        )
        VALUES ($1, $2, $3, $4)
        RETURNING id
        "#,
    )
    .bind(event_type)
    .bind(decision_lease_id)
    .bind(decided_by)
    .bind(payload)
    .fetch_one(&self.pool)
    .await?;
    let id: i64 = row.try_get("id")?;
    Ok(id)
}
```

**沿用既有 `EarnMovementError`**（`PgError(#[from] sqlx::Error)` 已涵蓋 INSERT 失敗與 CHECK constraint 違反）。不新增 error variant——CHECK 違反會是 `sqlx::Error::Database`，落 `PgError`，caller 一律 fail-closed，語意足夠。

### 3.2 欄位清單 → V035 column 對應

只寫 4 個 NOT NULL / load-bearing 欄，其餘 nullable 欄靠 DB DEFAULT（與 Python `handoff_audit.py` 對非 review 事件把 psr_*/expected_* 全填 NULL 的範式一致，但 Rust 端直接省略讓 DEFAULT 生效更乾淨）：

| 寫入欄 | V035 型別 | 值來源 | 備註 |
|---|---|---|---|
| `event_type` | TEXT NOT NULL CHECK(26-enum) | §7 決策值 | **必在 CHECK 白名單內，否則 INSERT fail-loud** |
| `decision_lease_id` | TEXT NULL | earn `lease.as_str()` | 審計鏈 join：earn_movement_log ↔ lease_transitions ↔ 本表 |
| `decided_by` | TEXT **NOT NULL** | `payload.actor_id`（operator role）| GT-9；空字串禁止 |
| `payload` | JSONB NULL | 見 §3.3 | approval_id UUID 寫這裡 |
| `id` | BIGSERIAL (PK part) | DB nextval | `RETURNING id` 取回 |
| `ts` | TIMESTAMPTZ NOT NULL DEFAULT now() | DB DEFAULT | 不顯式寫 |
| `rule_failures` / `lease_revoke_triggers` | TEXT[] NOT NULL DEFAULT '{}' | DB DEFAULT | 不顯式寫 |
| 其餘 (candidate_id / verdict_* / psr_* / expected_* / cost_* / lease_ttl_ms ...) | 全 NULL-able | 省略 | DB 存 NULL |

### 3.3 approval_id（String UUID）寫入哪個 forensic 欄

**寫入 `payload` JSONB**（不是 `decision_lease_id`）。理由：`decision_lease_id` 語意 = Decision Lease 的 id（earn 的 `lease_id`），而 `approval_id` 是 authorization.json UUID（`mod.rs:145-146`），兩者不同物。approval_id 屬 forensic 上下文，`payload` 是 V035 明列的「forward-compat replay payload」欄，正是它的歸屬。

`payload` 建議 shape（E1 可微調鍵名，但這 4 鍵 load-bearing）：
```json
{
  "earn_direction": "stake",            // stake | redeem
  "approval_id": "<UUID from EarnIntentPayload.approval_id>",
  "intent_id": "earn-EARN_STAKE-<symbol>-<approval_id>-<actor_id>",
  "amount_usdt": "<payload.amount_usdt>",
  "engine_mode": "demo",
  "api_scope_used": "account:earn:write"
}
```

### 3.4 審計鏈閉環（設計意圖兌現）

寫入後 `insert_governance_audit_log` 回傳的 `id: i64` → 注入 `insert_placeholder(..., governance_approval_id=id, ...)`。此後 `lookup_governance_approval(id)`（GT-4）能反查到**真 row**（不再是解不到的 id=0）。lineage 完整性缺口關閉。

---

## 4. scope item (2) — `dispatch_earn_intent` 插入 hop + fail-closed 分支

### 4.1 插入位置

在 **Gate E-6 的 `insert_placeholder` 之前**（`earn_router.rs:365-397`），新增一個 **Gate E-5.5**（命名建議，介於 amount parse 與 placeholder INSERT 之間）：

```
... Gate E-5 amount parse (:336-363) ...

// ─── Gate E-5.5: 先寫 governance_audit_log 取真 id（兌現 PA-DRIFT-6 鏈）──
let audit_payload = serde_json::json!({ ...§3.3 shape... });
let governance_approval_id: i64 = match writer
    .insert_governance_audit_log(
        earn_audit_event_type(intent.intent_type),  // §7.2(b) direction-based helper
        lease.as_str(),               // decision_lease_id
        &payload.actor_id,            // decided_by (NOT NULL)
        &audit_payload,
    )
    .await
{
    Ok(id) => id,
    Err(e) => {
        // fail-closed：不做 Bybit call、不寫 placeholder、guard Drop 釋放 Cancelled。
        // 絕不 fabricate id（禁 fallback 0 / 任何 placeholder id）。
        return IntentResult::rejected(
            EarnDispatchError::GovernanceAuditFailed(format!("{}", e)).to_string(),
        );
    }
};

// ─── Gate E-6: INSERT placeholder（改用真 id）──
let direction = direction_for_earn_intent_type(intent.intent_type);
let movement_id = match writer.insert_placeholder(
    direction, amount_f64, apr_at_time,
    governance_approval_id,   // ← 真 id，非 0
    engine_mode, api_scope_used,
).await { ... 既有 :389-397 不變 ... };
```

刪除 `earn_router.rs:376` 的 `let governance_approval_id: i64 = 0;`。

### 4.2 fail-closed 分支精確語意（鏡像既有 placeholder-fail :391-396）

audit-log INSERT 失敗時，**逐字對齊**現有 placeholder-fail 分支（`:391-396`）的結構：
1. **不做 Bybit call**（audit hop 在 Bybit place-order Gate E-7 之前）。
2. **不寫 placeholder**（audit row 是 placeholder 的前置，audit 沒寫成 placeholder 就不該寫）。
3. **lease 釋放 Cancelled**：此時 `lease_guard` 尚未呼叫 `consume_ok()` / `consume_failed()`，函數 `return` 觸發 `EarnLeaseGuard::drop`（`:161-174`）→ 自動 `release_lease(Cancelled)`。與 placeholder-fail 分支完全同機制（該分支也是靠 Drop 走 Cancelled，`:392` 註釋自述）。
4. 回 `IntentResult::rejected(reason)`，reason = 新增分類字串 `earn_dispatch_governance_audit_failed`（grep-friendly，對齊 `EarnDispatchError` 既有前綴慣例）。

**明確禁止 fabricate id**：失敗路徑**絕不** fallback 到 0 或任何 placeholder id。這正是本工作要消除的 sentinel；若失敗時回退 0，等於把 audit-lineage 缺口從「always 0」改成「sometimes 0」，更糟。fail-closed = reject 整個 intent。

### 4.3 新增 `EarnDispatchError` variant

```rust
/// governance_audit_log 先寫失敗（PG 不可達 / CHECK 違反）。
/// 此狀態下 Bybit call 尚未發起、placeholder 未寫；audit lineage 無法建立
/// 視為 fail-closed（絕不 fabricate id）。
#[error("earn_dispatch_governance_audit_failed: {0}")]
GovernanceAuditFailed(String),
```
並在既有 `earn_dispatch_error_display_strings_are_grep_friendly` test（`:671-701`）補一條斷言。

---

## 5. scope item (3) — 註釋 before/after 精確文字

### 5.1 `earn_router.rs:365-376` sentinel 註釋改寫

**BEFORE**（`:365-376`）:
```rust
    // ─── Gate E-6: INSERT placeholder row（earn_movement_log）─────────────
    // earn_governance §2.5「兩階段範式」：placeholder 寫 'pending'，Bybit ack 後
    // UPDATE outcome 'matched'；Bybit timeout 時 Daily cron 掃 24h pending 補對賬。
    // governance_approval_id 為 caller 端 INSERT 後傳入 i64 soft ref（PA-DRIFT-6）；
    // 本 IMPL approval_id 是 String UUID（per EarnIntentPayload）而非 BIGINT id，
    // writer 需 BIGINT — 採取 string→hash i64 fallback：approval_id 作為 audit
    // forensic 字串保留在 governance_audit_log，但 writer FK 端用 0（占位 sentinel）
    // 直到 W6/E1e 補 caller 端「先寫 governance_audit_log RETURNING id」chain。
    //
    // 注意：本決策是 Wave C carry-over → 留給 Wave D/E 補 governance_audit_log
    // INSERT chain；本 IMPL 文檔化此 sentinel 行為避 silent drift。
    let governance_approval_id: i64 = 0; // Wave D/E carry-over: TODO 接 governance_audit_log INSERT chain
```

**AFTER**（`:365` 起，`let ... = 0;` 整行刪除，改由 Gate E-5.5 提供真 id）:
```rust
    // ─── Gate E-6: INSERT placeholder row（earn_movement_log）─────────────
    // earn_governance §2.5「兩階段範式」：placeholder 寫 'pending'，Bybit ack 後
    // UPDATE outcome 'matched'；Bybit timeout 時 Daily cron 掃 24h pending 補對賬。
    // governance_approval_id 為 Gate E-5.5 先寫 governance_audit_log 取回的真實
    // BIGSERIAL id（soft ref，PA-DRIFT-6）；approval_id（String UUID）已作 forensic
    // 保留在該 audit row 的 payload JSONB。id 由上方 Gate E-5.5 綁定，此處直接用。
```

### 5.2 `:370` 誤導 hash-fallback 註釋移除

GT-6：代碼從未有 hash fallback，只是 `= 0`。上述 AFTER 已刪除「採取 string→hash i64 fallback」整句與「writer FK 端用 0（占位 sentinel）」句。**沒有 hash 代碼要拆**——只是刪誤導文字 + 改寫 sentinel 註釋。

---

## 6. scope item (4) — 失敗語義變更的顯式風險聲明（給 E3 / BB / operator）

**本改動把 `learning.governance_audit_log` 的 DB INSERT 引入 earn critical path 的 Bybit place-order 之前。**

- **今天**：帶 sentinel `governance_approval_id=0`，audit lineage 拿假 id，但 intent **照過**（governance_audit_log 是否可用完全不影響 earn 能否下單）。
- **改後**：若 `governance_audit_log` 不可用（PG 不可達 / CHECK 違反 / pool 耗盡），**所有 earn intent 現在都 reject**（Gate E-5.5 fail-closed），連 Bybit call 都不發。

**這是刻意的 fail-closed**，對齊：
- CLAUDE.md root principle 8「Every trade must be reconstructable and explainable」——沒有 audit row 就不該有 earn 動作。
- root principle 6「Uncertainty defaults to conservative behavior」。
- survival-first：earn stake/redeem 非交易熱路徑（operator-driven manual action，`earn_router.rs:581-583`），reject 的代價 = 一次 earn 操作延後，**遠低於** audit 缺 row 的治理代價。

**availability trade-off 必須 operator 白紙黑字接受**：earn 可用性現在**耦合** governance_audit_log DB 可用性。這對 earn 是可接受的（低頻、非救命路徑）；但若未來有人把此範式套到交易熱路徑，需重新評估（交易熱路徑不該因 audit DB 抖動而全 reject——那要 fail-soft + 告警，不同語意）。**本設計僅授權 earn 路徑，不設先例給熱路徑。**

---

## 7. RESOLVED（operator 拍板 2026-07-05）— event_type = (b) earn 專用值

**決策 = (b)**：加一支 V-migration 補 `earn_stake_approval` / `earn_redeem_approval` 兩值，event_type 層一級可濾、徹底閉合 audit lineage（不用 payload 二次判別）。operator 理由：CC-3 本質是修 audit-lineage 完整性，不應用「earn 事件混入 `lease_grant`」的較小缺口去換 sentinel 缺口；migration 走 V098/V113 老路、dry-run 有 gate、解凍時 E1→E2→E3→E4→deploy 整鏈本來就要跑，+1 migration 為邊際成本。

### 7.1 V-migration 規格（鏡像 V098 / V113 idempotent CHECK swap）

檔名：**`V150__governance_audit_log_earn_event_types.sql`**（已核 origin/main @`912bffd7f` 最大版號 = V149 → next free = V150）。

**baseline 核實（2026-07-05，origin/main）**：V113 之後**無任何 migration 修改** `governance_audit_log_event_type_check`（V114 僅唯讀 Guard probe，V137/V138 是別表的 event_type）→ 現行 CHECK = **V113 26-value canonical**，確定。V150 = 26 + `earn_stake_approval` + `earn_redeem_approval` = **28-value**。

V113 26-value canonical（V150 ADD CONSTRAINT 必原樣重現這 26 個再 +2）：
```
review_live_candidate, lease_grant, lease_auto_revoke, bulk_re_evaluation, audit_write_failed,
replay_handoff_request, replay_run_started, replay_run_cancelled, replay_manifest_verify_attempted,
replay_signature_test_key_blocked, replay_pid_identity_mismatch, replay_idor_admin_bypass,
replay_artifact_path_traversal_blocked, replay_argv_mismatch_blocked, lease_acquire_request,
lease_acquire_success, lease_acquire_fail, lease_release_consumed, lease_release_failed,
lease_release_cancelled, lease_sm_transition, halt_session_set, halt_session_auto_cleared,
halt_session_manual_cleared, pg_dump_completed, pg_dump_failed
```

- **Guard B**：先 assert `governance_audit_log_event_type_check` constraint 存在且含 V113 baseline 值（如 `halt_session_set` / `pg_dump_*`），否則 `RAISE EXCEPTION`「V053/V054/V098/V113 must deploy first」（照 `V113:89-98` 範式）。
- **Idempotent skip**：probe 現有 CHECK def，若 `earn_stake_approval` 已在 → `RAISE NOTICE ... skipping`（照 `V113:136-146`）。
- **Swap**：`LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE` → `DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check` → `ADD CONSTRAINT ... CHECK (event_type IN (...28 值...))`。28 值 = V113 canonical 26 + `earn_stake_approval` + `earn_redeem_approval`。
- **COMMENT ON CONSTRAINT** 更新為 28-value 說明（V113 26 + earn 2）。
- **強制 dry-run**：land 前 Linux PG double-apply（`feedback_v_migration_pg_dry_run`）；apply 兩次驗 idempotent（第二次應命中 skip NOTICE）。
- 配 mock test（照 `tests/migrations/test_v053_replay_event_types.py` 範式）：斷言含 `LOCK TABLE ... ACCESS EXCLUSIVE`、`DROP CONSTRAINT IF EXISTS`、`ADD CONSTRAINT`、兩 earn 值、`lock→drop→add` 順序。
- migration 是**獨立小 ticket**（走 PG dry-run 鏈），與 §3–§5 的 Rust 改動可分開 land，但 **migration 必先於 engine binary**（見 §7.3）。

### 7.2 event_type 由 direction 決定 → helper fn（非單一常量）

```rust
/// §7 決策 (b)：earn approval 專用 event_type，依 intent direction 分兩值。
/// 前置：V{next}__governance_audit_log_earn_event_types.sql 已 land（28-value canonical）。
fn earn_audit_event_type(intent_type: IntentType) -> &'static str {
    match intent_type {
        IntentType::EarnStake => "earn_stake_approval",
        IntentType::EarnRedeem => "earn_redeem_approval",
        _ => unreachable!("earn intent_type validated at Gate E-2"),
    }
}
```
Gate E-5.5 呼叫改為 `earn_audit_event_type(intent.intent_type)`（§4.1）。self-grep test 應鎖住兩 earn 值皆在源碼中。

### 7.3 部署時序（解凍後，E1/PM checklist 必鎖）

migration **先於** engine binary land：先 Linux PG double-apply `V{next}`（dry-run→apply），CHECK 進 28-value 後，**再** `restart_all --rebuild` 帶新 engine。順序反了（engine 先起）會使 earn intent 在 migration 未 apply 時命中舊 26-value CHECK → `GovernanceAuditFailed` fail-closed（reject）——雖安全，但 earn 全 down 直到 migration apply。因這是**跨 artifact 部署順序依賴**，QA 部署 sign-off 必列此序。

---

## 8. 副作用清單

| 問題 | 答案 |
|---|---|
| 有其他模塊 import earn_router / earn_movement_writer？ | earn_router 只被 `intent_processor::mod` 內用（`process_earn_intent`）；earn_movement_writer 被 `database/mod.rs:29` re-export + bootstrap 注入 + cron reader wrapper（Wave B 尚未接實 client）。新增 method 是 **additive**，不改既有簽名 → 無 caller 斷裂。 |
| 改動函數在哪些測試被 mock？ | `earn_reconciliation.rs` 的 `MockMovementReader` 實作 `EarnMovementReader` trait（`compute_local_net_flow` 等 3 method），**不含** `insert_governance_audit_log`（不在 trait 上）→ mock 不受影響。`EarnMovementWriter` 的既有 test 全是 SQL 字串 self-grep（`include_str!`），新增 method 只需補一條同型 test，不破既有。 |
| asyncio/threading 混用邊界？ | 無新增。`insert_governance_audit_log` 是 `async fn`，在既有 `dispatch_earn_intent`（已 async）內 await，同 tokio runtime。無 sync/async 跨界。 |
| 改 API response schema？ | 否。`IntentResult` 結構不變，只多一種 `rejected_reason` 字串值（`earn_dispatch_governance_audit_failed`）；GUI 顯示 reason 字串不需 schema 改動。 |
| 觸 RustEngine ↔ Python IPC schema？ | 否。全在 Rust engine 內，raw PG INSERT，不經 IPC。 |
| cron 相容非零 id？（E2 焦點③）| **相容，無改動**。`earn_reconciliation.rs` 的 WHERE 只 key on `reconciliation_status='pending'`（`earn_movement_writer.rs:395-396`），reader trait 完全不投影/過濾 `governance_approval_id`。今天過 sentinel 0，改後過真 id，cron 行為**不變**。書面確認即可，非改動。 |
| governance_audit_log 現有 producer 衝突？ | 否。append-only event log，多 producer 各寫各 event_type；earn 新增一種寫入不影響 Python 端既有 INSERT。 |

---

## 9. 降級 / rollback 路徑

- **Rollback = 純代碼 revert**（git revert 對 `earn_router.rs` + `earn_movement_writer.rs` 兩檔的 diff）。**0 schema 副作用**（走 (a) 時無 migration）；若走 (b)，migration 已 land 的 CHECK 值多兩個是 forward-compat additive，revert 代碼後多餘的 event_type 值不會 orphan（無人寫即無 row）。
- **Runtime 降級**：Gate E-5.5 失敗 = earn intent reject（fail-closed），engine 其餘功能（trading hot-path / 其他 intent）**完全不受影響**（earn 是隔離 dispatch entry，`process_earn_intent` 獨立於 `process_with_features`，`earn_router.rs:576-584`）。即「earn 降級」不擴散為「引擎降級」。
- **無需 --rebuild 之外的特殊部署**：純 Rust 改動，走 `restart_all --rebuild`（重建 engine binary，`feedback_restart_rebuild_flag_scope`）。若走 (b) 需先 Linux PG double-apply migration。

---

## 10. 代碼足跡 / LOC / 觸熱檔

| 檔 | 改動 | 估 LOC | 熱檔？ |
|---|---|---|---|
| `earn_movement_writer.rs`（680 行）| +`insert_governance_audit_log` method（~30 LOC）+1 self-grep test（~15 LOC）| +~45 | 是（governance hot path，遠低於 800 警戒）|
| `earn_router.rs`（704 行）| +Gate E-5.5 block（~20 LOC）+`GovernanceAuditFailed` variant（~4 LOC）+刪 `=0` 行 +改註釋 +test 補一斷言（~3 LOC）| +~25 −1 | 是（同上）|
| **合計** | | **~+70 LOC net** | 兩檔皆 <800，無破 cap |

**Rust 側：0 新檔 / 0 IPC / 0 API schema**；額外一支 §7.1 event_type CHECK V-migration（idempotent、~40 LOC SQL + mock test，走 PG dry-run 鏈，可獨立 land）。等效方案比較：走 Python audit-writer 路徑需新建 Rust→Python IPC method + 序列化 + Python 端加 RETURNING 支援 + 把 earn 綁死 control_api，讀碼與維護成本遠高。本方案（Rust raw INSERT 複用既有 pool + sibling 範式）是讀碼成本最低者。

---

## 11. E1 派發計劃（Wave D/E 解凍後）

**單 E1 串行即可**（兩檔有依賴：earn_router 的 Gate E-5.5 呼叫 earn_movement_writer 的新 method），LOC 小，不值得拆並行。

step-by-step：
1. **先 land §7.1 migration**（`V{next}__governance_audit_log_earn_event_types.sql`，獨立小 ticket，走 Linux PG double-apply dry-run）——CHECK 進 28-value 是後續 Rust 改動的前置。
2. `earn_movement_writer.rs`：新增 `insert_governance_audit_log`（§3.1）+ helper `earn_audit_event_type`（§7.2）+ self-grep test（斷言 SQL 含 `learning.governance_audit_log` / `RETURNING id`，且兩 earn event_type 值在源碼）。
3. `earn_router.rs`：新增 `EarnDispatchError::GovernanceAuditFailed`（§4.3）→ 插入 Gate E-5.5（§4.1）→ 刪 `:376 =0` → 改寫 §5 註釋 → 補 grep-friendly test 斷言。
4. `cargo test --release --lib`（earn 相關 + writer + router 全綠）。
5. **不 deploy**（本設計 DORMANT）；解凍後由 PM 決定部署時序，且 migration 必先於 engine binary（§7.3）。

---

## 12. E2 / E3 / BB 復核焦點清單（可勾選）

**E2（對抗審查）**
- [ ] Gate E-5.5 fail 分支**確實**走 `return` 觸發 `EarnLeaseGuard::drop` → Cancelled（逐行對齊 placeholder-fail `:391-396`），**未** consume_ok/consume_failed。
- [ ] fail 分支**絕不** fallback id=0 或任何 placeholder id（grep `= 0` 應只剩不相關處；`governance_approval_id` 賦值唯一來源 = Gate E-5.5 的 `Ok(id)`）。
- [ ] `decided_by` 傳 `payload.actor_id`，**非空字串**（V035 NOT NULL）；amount parse fail（Gate E-5）在 audit hop 之前，順序未倒。
- [ ] `earn_audit_event_type` 兩值（`earn_stake_approval`/`earn_redeem_approval`）在 §7.1 migration 後的 **28-value** CHECK 白名單內；self-grep test 鎖住表名 + RETURNING id + 兩 earn 值。
- [ ] cron 相容確認（焦點③）：`earn_reconciliation.rs` reader trait 無 governance_approval_id 投影，WHERE 僅 `reconciliation_status='pending'`——書面 sign-off，無改動。

**E3（governance / 失敗語義）— 因改 earn 失敗語義，必走**
- [ ] 接受 §6 availability trade-off：governance_audit_log 不可用 → earn intent 全 reject（刻意 fail-closed）。
- [ ] 確認此語義**僅授權 earn 路徑**，不設先例給交易熱路徑。
- [ ] fail-closed 路徑不觸五 live gate / 不改 lease 授權語意 / 不觸 live_execution_allowed（本改動與三硬邊界正交）。

**BB（exchange-facing）— earn 走 Bybit Earn API，必走**
- [ ] audit hop 在 Bybit place-order（Gate E-7）**之前**，不改 Bybit 呼叫參數 / retCode 處理 / write_failure 路徑（`:478-549` 不動）。
- [ ] Bybit timeout / retCode!=0 的既有 fail-closed（§5.1）不受 audit hop 影響——audit 已成功寫、id 已綁，Bybit fail 仍走 write_failure（此時 write_failure 亦用真 id，不再是 0）。

**建議工作鏈**：`PM → PA(本文) → MIT(§7.1 migration Guard/dry-run 審) → E1 → E2 → E3(governance) → BB(exchange-facing) → E4 regression → QA(跨-artifact 部署順序 §7.3 sign-off) → PM`。migration 因涉 V### CHECK swap，MIT + Linux PG double-apply dry-run 為必經（`feedback_v_migration_pg_dry_run`）。

---

## 13. 硬邊界 / 16 原則合規速記

- 未觸三硬邊界（`live_execution_allowed` / `max_retries` / `system_mode`）——本改動與之正交。
- root principle 1（單一寫入口）：不違反——指訂單執行寫入口；governance_audit_log 是 append-only 多 producer event log（B 型，§1）。
- root principle 8（可重構可解釋）：**正向強化**——補上缺失的 audit lineage id。
- Rust-first（`feedback_new_code_rust_first`）：合規——新 method 純 Rust + PyO3-free，複用既有 pool。
- fail-closed 設計鐵則：合規——失敗 deny + reject，**禁 fabricate id**（§4.2）。

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-05--cc3_earn_governance_audit_id_chain_design.md
