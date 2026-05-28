# E1 IMPL — Wave 5 Packet C 全 Rust 對抗審查 MED-1 / MED-2 / LOW-1 hardening

- 日期：2026-05-28
- 來源：E2 adversarial review 2026-05-28 verdict APPROVE-WITH-CONDITIONS
- 範圍：MED-1（console_banner tmp 檔名 uniquifier）+ MED-2（SharedFailsafeWatcher 並發 idempotent guard）+ LOW-1（EmailConfig Debug secret redaction）
- 不在本 task：HIGH-1（banner channel weight）退 PA Sprint 3

## 任務摘要

修 E2 全 Rust 對抗審查的三項 concurrency + secret hardening finding。三項皆在
`notification_failsafe` 模塊內，互不重疊。完成後等 E2 re-review + E4 regression。

## 修改清單

| 檔 | 改動 | 行為 |
|---|---|---|
| `dispatchers/console_banner.rs` | tmp 檔名加 process_id + nanos + AtomicU64 counter 三重後綴 + 新增 T11 並發測試 | 同進程並發寫各自獨立 tmp，rename 各自 atomic |
| `providers/single_watcher.rs` | `check_timer` 把 idempotent guard claim 從 Step 3 re-lock 移到 Step 1 同鎖內 + 新增 T4.12 並發測試 + CountingAudit mock | 並發呼叫只一次 escalate |
| `dispatchers/email.rs` | `EmailConfig` 移除 `derive(Debug)` 改手寫 redact impl + 新增 T15 測試 | `{:?}` 不洩漏 smtp_app_password / fingerprint 明文 |

diff stat：3 檔 / +251 / -18。

## 關鍵 diff

### MED-1 — console_banner.rs tmp uniquifier

根因：原 tmp path `failsafe_banner_active.json.tmp.<pid>`，`pid` 同進程恆定。
`write_banner` 與 `clear_banner` 都走 `write_payload` 寫同一 tmp，並發時 two
writers 共用同一 tmp，atomic rename 失效（一方半寫內容可能被另一方 rename 出去）。

修法：tmp 檔名改 `...tmp.<pid>.<nanos>.<seq>`，`seq` 來自進程級 `static
TMP_COUNTER: AtomicU64`（`fetch_add(1, Relaxed)` — 只需唯一性不需順序）。process_id
保留（跨進程辨識），nanos + counter 解決同進程並發。

驗：T11 並發 16 路（write_banner / clear_banner 交錯）後 final 檔必能完整 parse，
且不殘留任何 `.tmp.*` 檔（每個 rename 都消費掉自己的 tmp）。

### MED-2 — single_watcher.rs check_timer claim-before-await

根因：`check_timer(&self)` 三段拆鎖（lock → drop → await → re-lock per spec §4.7）；
idempotent guard `escalated_for_current_arm` 原本在**最後 re-lock 才 set**。`&self`
容許並發呼叫（C4 spawn 多 tick / 重入），兩個並發呼叫可都在 Phase1 看到
`timer_expired == true`（flag 尚未 set）→ 各自 drop 鎖去 await → double SM-04
transition + double audit。

修法：把 claim 提前到 Step 1 同一個 lock hold 內：

```rust
let claimed = {
    let mut state = self.state.lock();
    if timer_expired(&state, now_ms, FailsafeConfig::DEFAULT_TIMEOUT_MS) {
        state.set_escalated_for_current_arm(true);  // ← 同鎖內立刻 claim
        true
    } else {
        false
    }
}; // drop lock
if !claimed { return None; }
// Step 2 無鎖跑 escalation（flag 已 set，不再 re-lock）
```

第二個並發呼叫 re-lock 時看到 flag 已 set → `timer_expired` 回 false → 不重觸發。
mutex 序列化把「判定 + 佔用」原子化。`set_escalated_for_current_arm` pub(crate)
setter 語義不變（仍只 crate 內可寫）。原 Step 3 re-lock 段移除（claim 已在 Step 1）。

驗：T4.12 並發 16 路 check_timer 對「已武裝且到期」timer，斷言 `Some` 恰好 1 次 +
audit emit 恰好 1 次 + 後續再 check 回 None。**對抗驗證**：臨時還原 buggy 版（claim
留 Step 3 + `tokio::task::yield_now()` 放大窗口）→ T4.12 FAIL（16 escalations
instead of 1）→ 證明 test 抓得到 race；隨即還原修法版 PASS。

### LOW-1 — email.rs EmailConfig Debug redaction

根因：`EmailConfig` `derive(Debug)` 持 `smtp_app_password`，任何 `{:?}`（log /
tracing / panic / 巢狀結構）一旦印它就洩漏。latent（當前無 log 印它）。

修法：移除 `derive(Debug)`，手寫 `impl std::fmt::Debug`：`smtp_app_password` 與
`fingerprint`（sha256 衍生敏感值）都印 `***REDACTED***`，其餘欄位正常。

驗：T15 斷言 Debug 輸出不含密碼明文 / fingerprint 明文，含 `***REDACTED***`，
非 secret 欄位（smtp_host / username）仍正常顯示（驗未過度 redact）。

## MED-2 escalate-fail flag 處理判斷

**判斷：escalate 失敗時 flag 不 reset。**

理由（已寫進 check_timer doc comment）：
1. survival 優先。`execute_failsafe_escalation` 內個別副作用（exchange sync / audit
   emit）失敗本就**不 rollback transition**（見 mod.rs `execute_failsafe_escalation`
   不變量）；失敗細節由回傳的 `FailsafeExecutionReport`（sync_records / audit_error）
   承載，交 caller / audit 記錄與告警，而非靠重觸發補救。
2. 若 escalate 失敗就 reset flag 讓下一 tick re-fire，會造成 double SM transition /
   double audit 噪音 — 正是 MED-2 要消除的問題。
3. 「同一次武裝只 escalate 一次」的真正重置點是 `evaluate_dispatch`（觀察到新一輪
   AllSuccess→AllFail）或 `record_operator_ack`（operator ack）— 這條路徑才 reset
   flag，符合 spec「同一次武裝一次 escalate」語義。

## 治理對照

- CLAUDE.md §二 原則 5（survival 優先）：MED-2 flag 不 reset 判斷 + LOW-1 fail-safe
  secret 不洩漏 + MED-1 atomic rename 不腐化 banner。
- CLAUDE.md §四 fail-soft 不 panic：三項皆無新 unwrap / panic（test 外）。
- 硬邊界：未碰 max_retries / live_execution_allowed / execution_authority /
  system_mode。
- 註釋默認中文（per `feedback_chinese_only_comments`）。
- 不接 pipeline_ctor（C4 範圍）。
- 不動 HIGH-1（banner channel weight 退 PA Sprint 3）。

## 驗證

- `cargo test -p openclaw_engine --lib notification_failsafe`：107 passed / 0 failed
  （baseline 104 + 3 新：T11 banner concurrent / T4.12 watcher concurrent /
  T15 email debug redaction）。
- 對抗驗證：MED-2 test 在 buggy 版 FAIL（16 vs 1）、修法版 PASS。
- `cargo clippy -p openclaw_engine --lib --no-deps`：我改的三檔 0 hit。
  唯一 hit `email.rs:199 doc_lazy_continuation` 是 pre-existing（commit 9bf71423
  RealSmtpTransport `build_transport` doc，line 199 不在我的 diff hunk 內：我的
  hunk 在 50 / 65-90 / 683+）。openclaw_core price_tracker.rs:132 deprecated_semver
  用 `--no-deps` 已隔離（非本 scope）。

## 不確定之處

- MED-2 並發 test 用「每 task 自帶 RiskGovernorSm + 共享同一 SharedFailsafeWatcher
  state/clock/audit」模型 `&mut RiskGovernorSm` 不可共享，這是 C4 reentrancy 的合理
  模型；真實 C4 是否會有多 task 共享同一 watcher 跑 check_timer，待 C4 wire 時確認
  task 數 = 1（single shared watcher per Q4.1），則 MED-2 修法是 defense-in-depth
  （即使 C4 保證單 task，claim-before-await 也讓重入安全）。
- email.rs:199 pre-existing clippy 是否順手修：未修（最小影響原則，不在本 task scope）；
  留 follow-up（若 PM 要清，一行加 indent 即可）。

## Operator 下一步

1. PM 派 E2 re-review（三項對齊 finding + 對抗驗證證據）。
2. E4 regression（全 lib test + 跨平台 build）。
3. QA / PM 統一 commit + push（鏈 E1→E2→E4→QA→PM）。
