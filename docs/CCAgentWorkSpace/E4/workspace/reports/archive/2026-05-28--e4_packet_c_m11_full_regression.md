# E4 Regression — Wave 5 Packet C (C1+C2+C3) + M11 cron + MED/LOW hardening

- **Date**: 2026-05-28 (Mac local) / Linux build via ssh trade-core
- **HEAD**: `575a0a94e5501539c992281ea4d79382109d534e`
- **Scope (累積至 575a0a94)**:
  - C1 dispatchers: slack / email / console_banner / three_way + RealSmtpTransport (lettre 0.11)
  - C2: audit_emitter (PgAuditEmitter) + V114 SQL (17-col hypertable, GRANT reorder + idempotency nested EXCEPTION)
  - C3 providers: wall_clock / position_provider / exchange_stop_sync / single_watcher
  - E2 review fix: MED-1 (tmp uniquifier) + MED-2 (claim-before-await + 對抗 test T4.12) + LOW-1 (EmailConfig Debug redact)
  - M11 cron install + echo fix
- **Mode**: 全 lib regression + 跑兩遍 non-flaky + 對抗 reproduction + 跨平台 build；無 commit、無 push

---

## §1 Test 結果（基準線追蹤）

| 引擎 / filter | run 1 | run 2 | baseline | delta | non-flaky |
|---|---|---|---|---|---|
| `cargo test -p openclaw_engine --lib` | 3575 / 0 / 1 ign | 3575 / 0 / 1 ign | 3569 | **+6** | ✅ |
| `cargo test --lib notification_failsafe` | 107 / 0 | (covered) | 104 | **+3** | ✅ |
| `cargo test -p openclaw_core --lib risk_gov` | 27 / 0 | (covered) | 27 | 0 | ✅ |

- **3569 → 3575 (+6)** = email RealSmtpTransport 3 新 test (T12/T13/T14) + MED/LOW hardening 3 新 test (T11 banner concurrent / T4.12 watcher concurrent / T15 email Debug redact)。完全對齊任務預期「3569 + 3 + 3 = ~3575」。
- **notification_failsafe 107** = 104 baseline + 3（T11 + T4.12 + T15）。對齊任務預期 107。
- **risk_gov 27** = 不變（Packet C 未碰 openclaw_core risk governor）。
- 跑兩遍兩次結果 byte-identical（3575/0/1ign），無 flaky。

---

## §2 無測試被刪 / ignore 來遮蓋失敗

| 檢查 | 結果 |
|---|---|
| `grep #[ignore]` in notification_failsafe (現狀) | **0** |
| `+#[ignore]` 新增 in Packet C diff (`a746df14..575a0a94`) | **0** |
| `-fn test_` / `-#[test]` / `-#[tokio::test]` (移除既有測試) | **0** |
| Packet C diff stat (rust/ + sql/) | 16 檔 / **+4230 / -1**（-1 = Cargo.toml 行移，非 test 刪） |

全部 16 檔皆為**新增模塊**（notification_failsafe 全新 + V114 SQL + Cargo dep），**未修改 / 未刪除 / 未 ignore 任何既有 test**。baseline ratchet +6 全來自新增 test，非改既有 assertion 遮蓋失敗。符合 protocol 反模式禁線。

---

## §3 對抗 test 真實性核驗（MED-2 T4.12）

### 3.1 T4.12 是真並發（非 mock 假過）
- `#[tokio::test(flavor = "multi_thread", worker_threads = 4)]` — 真 4-thread runtime，非單 task fake-concurrent。
- 16 個真 `tokio::spawn`，全部 clone 同一 `Arc<SharedFailsafeWatcher>`（共享 parking_lot mutex state）。
- clock 在 spawn **之前** advance 過 `DEFAULT_TIMEOUT_MS + 1`，16 task 真競爭「armed + expired」的判定+claim。
- 斷言真實：`some_count == 1`（恰好一次回 Some）+ `CountingAudit.emit_count == 1`（`fetch_add` 真計數，非 stub 恆定回值）；隨後 re-check 回 None 且 count 仍 1。

### 3.2 E4 親自對抗 reproduction（核心證據）
臨時把 `check_timer` 還原成 buggy 版（claim `set_escalated_for_current_arm(true)` 從 Step 1 同鎖移到 await **之後** Step 3 re-lock，並加 `tokio::task::yield_now().await` 放大 race 窗口）→ 跑 T4.12：

```
test ...::t4_12_concurrent_expired_escalates_exactly_once ... FAILED
assertion `left == right` failed: 並發到期 check_timer 應恰好一次回 Some（idempotent claim 守衛）
  left: 16
 right: 1
```

**精確復現 E1 報告的「16 escalations instead of 1」**。隨即還原修法版 → T4.12 PASS（1 passed）；`git diff single_watcher.rs` = empty（零殘留還原）。**證明 T4.12 確實抓得到 race，不是 mock 假過 / false-pass**。

### 3.3 dispatchers mock 不掩蓋真實 send 邏輯
- `StubTransport`：`send()` 捕捉 envelope (`captured.push`) + 回 `!force_fail`（`new()` success / `new_failing()` false）→ 只 stub IO sink，業務邏輯（EmailDispatcher config 校驗 / 10s timeout 包裝 / fail-soft 轉 false）真跑。
- `CountingAudit` / `NoopDispatcher` / `EmptyPositions` / `NoopExchange`：同理只 stub trait IO 邊界，watcher 的 claim-before-await guard / SM transition 邏輯真跑。
- 符合 protocol mock safety rule §5.2（mock IO 邊界，不 mock 業務邏輯）。

---

## §4 clippy

| 命令 | notification_failsafe hit |
|---|---|
| `cargo clippy -p openclaw_engine --lib`（default lint set，protocol 標準）| **0** |

### Pre-existing / 標記
- **`email.rs:199 doc_lazy_continuation`**: default clippy = **0 hit**；只在 `cargo clippy --lib --no-deps`（升級 lint config，帶 pedantic/doc lint）下 fire。
  - git blame: commit `9bf71423`（本 Wave email RealSmtpTransport amend）→ 技術上是本 Wave 引入，非更早 pre-existing。
  - 性質：doc-comment 縮排 cosmetic（line 199 標題句接在 bullet list 後，需空白行或縮排）；0 業務影響。
  - 判定：**標 E1 cosmetic follow-up**（E4 不改鏈內 source file，守 E4 邊界）。修法 = line 198/199 間加一行 `///` 空白即解。
- **`openclaw_core price_tracker.rs:132 deprecated_semver`**: commit `ece31b69`，非本 scope；`--no-deps` 隔離後 0 hit；pre-existing 非本輪 regression。

---

## §5 build 完整性 + dependency tree

| 檢查 | 結果 |
|---|---|
| `cargo build -p openclaw_engine` (dev, Mac arm64) | **PASS** — 1 pre-existing dead_code warning `spawn_position_reconciler`（per E4 memory 2026-05-22，非本 scope）|
| Linux x86_64 `cargo build --release -p openclaw_engine` (ssh trade-core, `bash -lc`) | **PASS** — finished 44.92s，同 1 pre-existing dead_code warning |
| `cargo tree -p openclaw_engine | grep -ci openssl` | **0** ✅ |
| `grep -ci native-tls` | **0** ✅ |
| lettre 版本 | **v0.11.22**（spec 0.11）|
| `grep -ci aws-lc` | **3** — pre-existing（rustls default feature `aws_lc_rs`，非 lettre 引入；E1 §7.2 `git stash` baseline 對比已確認）；openssl=0 不受此影響 |

**結論**：lettre 0.11 + aws-lc-rs（aws-lc-sys 需 CMake + C compiler）在 Mac arm64 + Linux x86_64 雙平台 build clean；純 rustls 不引 openssl/native-tls，守「零 openssl sys-dep」目標。新 top-level dep 跨平台可移植性確認。

---

## §6 V114 schema 對齊（audit_emitter Rust-side）

- V114 CREATE TABLE = **17 column**：id, ts_ms, event_type, trigger, initiator, from_level, to_level, transition_succeeded, transition_skipped_reason, adjustments_count, sync_records, atr_buffer_multiplier, now_ms, acked_at_utc, acked_by, payload_jsonb, created_at。
- audit_emitter.rs INSERT 供 **13 column**（engine-writable）；正確省略 4 DB-controlled：`id`(BIGSERIAL) / `acked_at_utc` / `acked_by`（GUI ack UPDATE 路徑填）/ `created_at`(DEFAULT now())。
- `EMIT_TIMEOUT: Duration = Duration::from_secs(5)` const 確認（非 hot path；fail-soft margin per module rationale）。
- schema drift guard test（已在 107 內綠）：
  - `test_insert_sql_locked_table_name`（grep V114 表名）
  - `test_insert_sql_locked_columns_match_v114_schema`（grep 13 INSERT column）
  - `test_insert_sql_has_13_placeholders`（$1..$13）
- **V114 runtime idempotency 雙跑由 MIT 第三輪 Linux trade-core dry-run 驗（不在 E4 範圍）** — E4 只確認 Rust-side SQL 字串對齊 17-col schema。

---

## §7 跨語言浮點 / SLA

- notification_failsafe 無跨語言浮點 hot path（純 Rust + PG audit）→ 1e-4 一致性測試 N/A。
- fail-safe escalation 非 tick hot path（H0 Gate / Tick path / IPC SLA 不適用）；V114 INSERT 5s timeout 是 fail-soft margin 非 SLA 硬限。
- 結論：本 scope SLA / 浮點一致性 **不適用**（per 任務 §4 預判一致）。

---

## §8 M11 cron（補充）

| 檢查 | 結果 |
|---|---|
| `bash -n install_m11_replay_runner_cron.sh` | PASS |
| `bash -n m11_replay_runner_daily_cron.sh` | PASS |

M11 是 shell 腳本（daily 04:00 UTC smoke heartbeat），不影響 Rust/Python test baseline；echo auto-resolve fix（`faf7c06c`）含在範圍。runtime cron install 屬 operator/Linux hand-action。

---

## §9 結論

**PASS** — 全綠，跑兩遍 non-flaky，對抗 reproduction 確立 T4.12 真實性，跨平台（Mac arm64 + Linux x86_64）build clean，無測試被刪/ignore。可進 QA / PM 統一 commit。

### Carry-over（不阻 PASS）
1. **email.rs:199 `doc_lazy_continuation`** — E1 cosmetic follow-up（default clippy 0 hit，只 pedantic config fire；本 Wave `9bf71423` 引入；加一行 `///` 空白即解）。
2. **V114 runtime idempotency 雙跑** — MIT 第三輪 Linux trade-core dry-run（前置：operator DROP 第二輪 dirty 殘留表）。
3. **C5 `failsafe_ack_role` restricted role** — Sprint 3（GUI ack 路徑前置）。

### 退回 E1 修復清單
無（0 FAIL）。
