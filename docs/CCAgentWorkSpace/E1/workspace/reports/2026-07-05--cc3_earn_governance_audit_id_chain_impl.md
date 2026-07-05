# CC-3 / OOS-1 — Earn governance_audit_log id chain 實作報告

STATUS: DONE
Author: E1 · Date: 2026-07-05 · Worktree: `/Users/ncyu/Projects/TradeBot/cc3-worktree`（detached @ origin/main `912bffd7f`）
Chain: PA(design) → **E1(本報告)** → E2 → E3(governance) → BB → E4 → QA → PM
Design SSOT: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-05--cc3_earn_governance_audit_id_chain_design.md`

---

## 1. 任務摘要

兌現 PA-DRIFT-6 sentinel（`earn_router.rs:376` 的 `governance_approval_id = 0` audit-lineage 缺口）。
嚴格照 PA 設計 §3/§4/§5/§7 實作 4 交付物，未擴 scope。核心 = earn intent 在 Bybit
place-order 之前先 raw INSERT `learning.governance_audit_log` 取真 BIGSERIAL id 注入
earn_movement_log soft-ref；失敗 fail-closed（絕不 fabricate id）。event_type 由 direction
決定分兩值，配一支 idempotent V150 CHECK-swap migration（26→28 value）。

---

## 2. 修改清單（4 交付物，全在 worktree）

| # | 檔 | 動作 | LOC |
|---|---|---|---|
| 1 | `sql/migrations/V150__governance_audit_log_earn_event_types.sql` | 新檔（鏡 V113） | +166 |
| 2 | `tests/migrations/test_v150_earn_event_types.py` | 新檔（鏡 test_v053） | +196 |
| 3 | `rust/openclaw_engine/src/database/earn_movement_writer.rs` | +`insert_governance_audit_log` method +1 self-grep test | +72 |
| 4 | `rust/openclaw_engine/src/intent_processor/earn_router.rs` | +`GovernanceAuditFailed` variant +`earn_audit_event_type` helper +`EarnLeaseGuard::lease_id_str()` +Gate E-5.5 block +刪 `=0` +改註釋 +2 test 斷言 | net +~70 −14 |

無 migration 註冊表需更新：migrations 由 `migrations.rs::load_migrations_from_dir`（`read_dir` 掃描）自動發現，非 hardcode embed list；`REF-20_RESERVATION.md` / `README.md` 皆不列 V113+ 個別 migration（V149 亦未登記）。故僅落檔即足，對齊上次 V149 做法。

---

## 3. 關鍵片段

### 3.1 V150 ADD CONSTRAINT（28-value，26 原樣 + earn 2）

```sql
LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;
EXECUTE 'ALTER TABLE learning.governance_audit_log DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check';
ALTER TABLE learning.governance_audit_log
    ADD CONSTRAINT governance_audit_log_event_type_check
    CHECK (event_type IN (
        -- V113 26-value canonical 原樣重現（review_live_candidate ... pg_dump_failed）
        ...,
        'pg_dump_completed',
        'pg_dump_failed',
        -- V150 NEW (CC-3 / OOS-1):
        'earn_stake_approval',
        'earn_redeem_approval'
    ));
```
Guard A（V035 表存在）+ Guard B（`halt_session_set`[V098] + `pg_dump_completed`[V113] 雙探，缺任一 RAISE）+ idempotent skip（兩 earn 值已在 → RAISE NOTICE skip）+ COMMENT ON CONSTRAINT 更新為 28-value。

### 3.2 新 method 簽名（earn_movement_writer.rs）

```rust
pub async fn insert_governance_audit_log(
    &self,
    event_type: &str,
    decision_lease_id: &str,
    decided_by: &str,
    payload: &JsonValue,
) -> Result<i64, EarnMovementError>
// INSERT INTO learning.governance_audit_log (event_type, decision_lease_id, decided_by, payload)
// VALUES ($1,$2,$3,$4) RETURNING id
```
沿用既有 `EarnMovementError`（CHECK 違反/PG 不可達皆落 `PgError`），不新增 variant。

### 3.3 Gate E-5.5（earn_router.rs，Gate E-6 之前）

```rust
let audit_payload = serde_json::json!({
    "earn_direction": direction_for_earn_intent_type(intent.intent_type),
    "approval_id": payload.approval_id,
    "intent_id": intent_id,
    "amount_usdt": payload.amount_usdt,
    "engine_mode": engine_mode,
    "api_scope_used": api_scope_used,
});
let governance_approval_id: i64 = match writer
    .insert_governance_audit_log(
        earn_audit_event_type(intent.intent_type),
        lease_guard.lease_id_str(),   // decision_lease_id
        &payload.actor_id,            // decided_by (NOT NULL)
        &audit_payload,
    )
    .await
{
    Ok(id) => id,
    Err(e) => {
        // fail-closed：不做 Bybit call、不寫 placeholder；guard 未 consume_*，
        // return 觸發 EarnLeaseGuard::drop → release Cancelled。絕不 fabricate id。
        return IntentResult::rejected(
            EarnDispatchError::GovernanceAuditFailed(format!("{}", e)).to_string(),
        );
    }
};
```
`governance_approval_id` 現只在此綁定，Gate E-6 placeholder（:447）與 Gate E-9 write_failure（:576）皆用此真 id（write_failure 不再是 0）。`:376 let ... = 0;` 已刪。§5 誤導 hash-fallback 註釋已移除（grep `hash|占位 sentinel|string→hash` = 0 命中）。

---

## 4. 治理對照

- **硬邊界**：未觸 `live_execution_allowed` / `max_retries` / `system_mode`（正交）。未改 5-gate、未改 lease 授權語意、未改 API/IPC schema。
- **Guard A/B/C**：V150 含 Guard A（V035 表存在）+ Guard B（V113 26-value baseline 雙探）；Guard C N/A（無新 index）。
- **fail-closed 鐵則**：audit INSERT 失敗 = reject 整個 earn intent，絕不 fabricate id / 絕不 fallback 0（設計 §4.2）。逐字對齊既有 placeholder-fail 分支的 Drop→Cancelled 機制。
- **root principle 8**（可重構可解釋）：正向強化，補上缺失 audit lineage id。
- **root principle 1**（單一寫入口）：不違反——指訂單執行寫入口；governance_audit_log 是 B 型 append-only 多 producer event log（設計 §1）。
- **V035 column 對照親證**：`event_type`(CHECK)、`decision_lease_id TEXT NULL`、`decided_by TEXT NOT NULL`、`payload JSONB NULL`、`id`(BIGSERIAL PK part) 皆存在且 nullability 匹配 INSERT。`decided_by` 綁 `actor_id`（operator role），非空。
- **注釋規範**：新註釋全中文（bilingual-comment-style），fail-closed rationale 說明「為什麼」。

---

## 5. 驗證結果（Mac 本地，誠實計數）

| 驗證 | 命令 | 結果 |
|---|---|---|
| Rust 全 lib | `cargo test --release --lib` | **4324 passed / 0 failed / 1 ignored / 0 warnings**（baseline 未變） |
| earn 相關 | `cargo test --release --lib earn` | 153 passed / 0 failed（含新 `earn_audit_event_type_maps_stake_and_redeem`、`test_insert_governance_audit_log_sql_target`、augmented grep-friendly test） |
| Python V150 mock | `pytest tests/migrations/test_v150_earn_event_types.py -q` | **8 passed** |
| Python 全 migration mock | `pytest tests/migrations/ -q` | 226 passed / 2 skipped（skip 為 pre-existing，非本次） |

cargo 環境：本機 `~/.cargo/bin/cargo` symlink 鏈斷（→rustup→`/opt/homebrew/bin/rustup-init` 已不存在），改直呼 `~/.rustup/toolchains/stable-aarch64-apple-darwin/bin/{cargo,rustc}` + 該 bin dir 前置 PATH 才能跑（純環境問題，非碼問題）。

---

## 6. 偏離設計之處（顯式標明）

1. **`EarnLeaseGuard::lease_id_str()` 新增（設計未列的最小安全解）**：設計 §4.1 示例用 `lease.as_str()` 直取 lease id 作 `decision_lease_id`，但現碼 `lease` 已在 `EarnLeaseGuard::new(governance, Some(lease))`（:334）被 move 進 guard，raw `lease` binding 不再可達。故加一個非消耗式 `fn lease_id_str(&self) -> &str`（acquire 成功後 lease 恆 Some，保守 `unwrap_or("")` 避 panic）。語意等價設計意圖，改動面積最小。
2. **earn_router 補一條 helper unit test**（`earn_audit_event_type_maps_stake_and_redeem`）：設計 §7.2 要求「self-grep test 鎖住兩 earn 值皆在源碼」。writer 端 self-grep 鎖 SQL 表名+RETURNING id；兩 earn 字面值住在 router helper，故在 router 補一條與既有 `direction_for_*` helper test 同型的斷言。in-scope 加固，不擴 baseline 語意。

無其他偏離。26-value canonical 原樣照抄未增未刪未改。

---

## 7. 自評風險點（給 E2 / E3 / BB / E4 / QA）

- **fmt debt（非本次引入）**：`cargo fmt --check` 在本兩檔報的 diff 全落在 **pre-existing 未觸行**（earn_movement_writer.rs:124/375/519/735/743 等；earn_router.rs:145 等），我新增碼零新 diff。repo baseline 本就 fmt-drift；依 surgical-changes 原則未順手重排 pre-existing 行。E2 若要求全檔 fmt-clean 需另開 cleanup ticket（會擴大 diff，非 CC-3 scope）。standalone `rustfmt` 與 `cargo fmt` config 不同，以 cargo fmt 為準。
- **PG dry-run 未做（按分工）**：V150 的 Linux PG double-apply（`feedback_v_migration_pg_dry_run`）由 MIT 負責，我未跑（prompt 明示不跑 migration）。mock test 僅驗 SQL 結構契約，非 PG runtime 語意；Guard B 的 `pg_get_constraintdef` 反射、ACCESS EXCLUSIVE lock 行為、idempotent 二次 apply 命中 skip NOTICE 須 Linux 實證。
- **部署時序依賴（§7.3）**：V150 migration 必先於 engine binary land。順序反了（engine 先起、CHECK 仍 26-value）→ earn intent 命中 Gate E-5.5 fail-closed reject（雖安全，但 earn 全 down 直到 migration apply）。QA 部署 sign-off 必列此跨-artifact 順序。
- **availability trade-off（§6，給 E3）**：earn 可用性現耦合 governance_audit_log DB 可用性（刻意 fail-closed）。僅授權 earn 路徑，不設先例給交易熱路徑——需 E3 governance sign-off 白紙黑字接受。
- **BB 焦點**：audit hop 在 Bybit place-order（Gate E-7）之前；未改 Bybit 呼叫參數 / retCode 處理 / write_failure 路徑（:478+ 不動，僅其 `governance_approval_id` 引數改用真 id）。
- **cron 相容（E2 焦點③）**：`earn_reconciliation.rs` reader trait 不投影 governance_approval_id，WHERE 僅 `reconciliation_status='pending'`；今過 0、改後過真 id，cron 行為不變（書面確認，無改動）。

---

## 8. Operator / PM 下一步

1. E2 對抗審查（設計 §12 E2 清單逐條）。
2. E3 governance sign-off（§6 availability trade-off + 僅授權 earn 路徑）。
3. BB exchange-facing sign-off（audit hop 在 place-order 之前，未改 Bybit 面）。
4. MIT / Operator：V150 Linux PG double-apply dry-run（trading_postgres / trading_admin / trading_ai）。
5. E4 全回歸。
6. QA：跨-artifact 部署順序（migration 先於 engine binary，§7.3）sign-off。
7. PM 統一 commit + push（強制鏈，E1 不 commit）。

E1 IMPLEMENTATION DONE: 待 E2 審查
EOF
