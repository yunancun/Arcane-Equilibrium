---
name: 2026-05-02 P0 sqlx migration hash drift incident
description: audit-p1-1 retrofit (e858ae2/6cb1c3b) 改 V028/V030/V031/V032/V034 file 加 Guard 但 _sqlx_migrations.checksum 沒同步；3C TOML restart 觸發暴露；治理盲點 = closure SOP 漏 engine restart 實測
type: project
originSessionId: f6f6c16c-3c99-47e7-9e9b-b70f05a78674
---
# 2026-05-02 P0 sqlx Migration Hash Drift Incident

## 時間線
- **2026-05-02 13:04** `e858ae2` audit-p1-1 retrofit Guard A/B for V028/V030/V031/V032/V034（CLAUDE.md §七 V023 silent-noop 補丁）
- **13:28** `6cb1c3b` round-3 又改 V031（view shape-guard for V034-applied state）
- **13:35** `0c97c9c` audit-p1-1 sign-off「Linux production PASS」—— **是 cargo test PASS，不是 engine restart sqlx migrate 實測**
- **18:35** 我跑 `restart_all --keep-auth` 想讓 3C TOML 生效 → engine startup ABORT：`sqlx migrate error: migration 28 was previously applied but has been modified`
- **19:42** P0 修復完成 + 3C TOML 生效

## Root cause
- sqlx 0.8.6 對「已 applied 的 migration」校驗 file SHA-384，**file 改 hash 就 drift → abort**
- `OPENCLAW_AUTO_MIGRATE=1` 沒 fallback
- 5 個 migration 同時 drift（V028/V030/V031/V032/V034），V033 clean，V035 是 LG-5 Wave 1 新加待 apply

## 治本（B 路徑）
- E1 寫 Rust binary `srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`（commit `bb6bf04` + `2c8f053` TTY guard）—— 借 sqlx::Migration::new() 算 SHA-384，不自寫
- 三層安全：`--i-understand-this-modifies-db` flag + 拒絕 `--auto-yes` 等 bypass + TTY guard（`std::io::IsTerminal`）+ pg_dump backup + interactive `Type COMMIT` prompt
- Backup 路徑：`/tmp/openclaw/backup/_sqlx_migrations_pre_repair_<ts>.sql`
- Apply 結果：5 個 row UPDATE rows_affected=1，COMMITTED；restart 後 V035 自動 apply（success=t hash bit-identical with file）

## 治理盲點（必修）
1. **audit closure SOP 漏「engine restart sqlx migrate 實測」** —— `0c97c9c` sign-off 寫「Linux production PASS」是 cargo test PASS 非 runtime restart
2. **未來 migration retrofit closure 必須包含**：
   - `restart_all --keep-auth` engine 起來 ≥60s 無 abort
   - `SELECT count(*) FROM _sqlx_migrations` 與預期版本數匹配
   - demo + live 兩 DB 各驗一次（live 沒授權跳過但要記錄）
3. **可寫 V036 healthcheck migration**（建議）：startup auto_migrate runner pre-flight diagnostic — 偵測 checksum drift 但 file 為 pure Guard 補丁（DO $$ + RAISE EXCEPTION heuristic）→ WARN 而非 abort，提示跑 repair binary

## 關鍵教訓
- **sqlx 0.8.6 SHA-384 raw bytes，無 normalization**（不 trim / 不 strip comments / 不 collapse newlines）
- **Mac cargo test ≠ Linux runtime sqlx migrate 驗證** —— 兩個是不同的 hash check 路徑
- **Mac 端不能驗 P0** —— 必須 ssh 進 Linux runtime 跑 restart_all 才暴露
- **`pg_dump` 在 binary 必須走 PATH**（`Command::new("pg_dump")`），不 hardcode `/usr/bin/`（跨平台）
- **互動 prompt 必加 `IsTerminal` guard** —— 避免 pipe 輸入繞過

## 影響
- ~67 分鐘 engine down（demo + live 都 stale）
- demo open positions 從 paper_state 恢復（ETHUSDT short / APEUSDT short / BUSDT short）
- live 因 authorization.json missing 不在 P0 範圍，operator 經 `POST /api/v1/live/auth/renew` 重新授權
- 連帶生效 3C TOML：`dynamic_stop.base_ratio = 0.25` + `per_strategy.funding_arb.stop_loss_max_pct_override = 3.0`

## 相關檔案
- Repair binary：`srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`（commit `bb6bf04` + `2c8f053`）
- Merge 到 main：`3681f83`
- E1/E2/E4 reports：`srv/docs/CCAgentWorkSpace/E*/workspace/reports/2026-05-02--p0_migration_checksum_repair_*.md`
- PA design report：inline (sub-agent agentId `afbc3b15a4f9a9aa6`，已過期)
- Backup file：`/tmp/openclaw/backup/_sqlx_migrations_pre_repair_20260502T174245Z.sql`（Linux only）
