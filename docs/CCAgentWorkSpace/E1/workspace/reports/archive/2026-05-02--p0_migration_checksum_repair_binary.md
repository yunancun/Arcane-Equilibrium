# E1 Report — 2026-05-02 — P0 sqlx migration checksum repair binary（dry-run 階段）

**Branch**：`fix/p0-2026-05-02-sqlx-migration-checksum-repair`
**Commit**：`bb6bf04`（pushed to origin，尚未 merge）
**Base**：`cc286d0` (`origin/main`)
**狀態**：完成 binary + `--verify` dry-run，等 E2 審查 → operator 確認 → `--apply` 階段。

---

## 任務範圍（PA plan B 路徑）

寫獨立 Rust binary 修復 V028/V030/V031/V032/V034 sqlx checksum drift（2026-05-02 18:35 engine startup abort 主因）。本輪僅 `--verify`，**不執行 DB UPDATE**。

## 修改

| Path | 動作 | 行數 |
|---|---|---|
| `rust/openclaw_engine/src/bin/repair_migration_checksum.rs` | 新增 | 555 |
| `rust/openclaw_engine/Cargo.toml` | 修改 | +11（新 `[[bin]]` 段） |

## `--verify` 結果（Linux trade-core）

```
# parsed_files = 34
# db_rows      = 33
# drift_count  = 5
# drift_versions = [28, 30, 31, 32, 34]
# pa_known_drift     = [28, 30, 31, 32, 34]
# pa_caught_by_binary = [28, 30, 31, 32, 34]   ← 全命中
# pa_missed_by_binary = []
# v033_verdict       = clean                   ← 先前未知，binary 給定論
```

完整 output：Linux `/tmp/openclaw/migration_checksum_verify.txt`（49 行）。

額外發現（非本任務範圍）：
- **V035** `governance_audit_log` 在 repo 但 DB 無 row（`MISSING_IN_DB`），可能是新 pending migration，等 PA/PM 確認。
- **V022** repo 無檔、DB 無 row（engine `LEGACY_APPLIED_MAX_VERSION = 23` 提及；歷史跳號）。

## 算法基礎

完全借用 sqlx 0.8.6 的 hash function，不自寫 SHA-384：
- `openclaw_engine::database::migrations::load_migrations_from_dir(&path)`
  → `sqlx::migrate::Migration::new(version, desc, type, sql, no_tx)`
  → `checksum = Sha384::digest(sql.as_bytes())`（raw UTF-8 bytes，無 normalization）

確保算法與 engine 啟動時的 `Migrator::run` checksum 比對 100% 一致。

## 安全機制（`--apply` 三層 + 拒絕旁路）

1. **必帶 ack flag** `--i-understand-this-modifies-db`，缺即 exit 2。
2. **顯式拒絕** `--auto-yes/--yes/-y/--force`。
3. **自動 pg_dump 備份** → `$OPENCLAW_DATA_DIR/backup/_sqlx_migrations_pre_repair_<ts>.sql`；失敗即 abort 不 UPDATE。
4. **Tx 內 SELECT** 印 in-tx state → stdin `Type COMMIT to apply, anything else to ROLLBACK`。
5. **`COMMIT` 輸入** = 提交；**其他輸入** = ROLLBACK（exit 5）。

## 治理對照

- ✅ CLAUDE.md §七 跨平台路徑（全 env var，無 `/home/ncyu` / `/Users/ncyu` 硬編碼）
- ✅ CLAUDE.md §七 雙語注釋（MODULE_NOTE / docstring / inline SAFETY / 不變量）
- ✅ CLAUDE.md §二 #6 fail-closed（DB 連不上 / pg_dump 失敗 / UPDATE 失敗 → abort）
- ✅ CLAUDE.md §二 #8 可審計（pg_dump backup + tx SELECT + 互動 prompt + 提交後讀回）
- n/a CLAUDE.md §七 SQL migration Guard A/B/C（不新增 migration）
- ✅ Singleton 無新增
- ✅ 檔案 555 行 < 800 警告線
- ✅ E1 啟動序列 + 完成序列遵守（profile / memory / report 齊備）

## E2 review 注意點（10 項）

1. 算法借用方式（不自寫 SHA-384）
2. DB URL 來源（engine 同源 secret_env）
3. `--apply` 三層安全 + ack flag + 互動 prompt
4. 顯式拒絕 auto-yes / force flag
5. 不修 migration file（無 write 路徑）
6. `--verify` 不寫 DB（early return 在 mode 檢查後）
7. 檔案大小 555 行
8. 雙語注釋齊備
9. 無新 singleton
10. 跨平台（Mac 編譯路徑未驗，建議 E2 順手 `cargo check`）

## 後續流程

E2 PASS → E4 回歸 → operator 在 Linux trade-core 執行 `--apply`（互動）→ engine restart 驗證 sqlx checksum 不再 mismatch → PM 統一 commit / merge / push（per CLAUDE.md §七 強制鏈）。

## 參考

- Source：`srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`
- Cargo 段：`srv/rust/openclaw_engine/Cargo.toml` 末尾 `[[bin]] repair_migration_checksum`
- 借用源：`srv/rust/openclaw_engine/src/database/migrations.rs:306` (`load_migrations_from_dir`)
- sqlx hash：`Sha384::digest(sql.as_bytes())` — sqlx-core 0.8.6 `migrate/migration.rs:25`
- Linux dry-run：`/tmp/openclaw/migration_checksum_verify.txt`
- Memory append：`srv/docs/CCAgentWorkSpace/E1/memory.md` 末尾
- claude_report：`srv/.claude_reports/20260502_p0_migration_checksum_repair_binary.md`
