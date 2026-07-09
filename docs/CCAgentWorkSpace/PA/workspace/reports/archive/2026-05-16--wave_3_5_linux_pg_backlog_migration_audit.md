---
report: PA Wave 3.5 — Linux PG backlog migration apply audit
date: 2026-05-16
auditor: PA
subject: Verify V081-V093 backlog Linux PG apply status before V094 IMPL kickoff
mode: Read-only Linux PG empirical + source tree compare（不修改 migration / runtime / config）
trigger: V094 spec §4.4 caveat + TODO §11.5 Wave 3.5 row（per F-FA-1 PA verdict 2026-05-15 commit `9b1117a0` 接續工作）
verdict: NEEDS-ACTION（V092 必補 + V091/V093 sqlx checksum repair + V081 confirm dead slot）
---

# PA Wave 3.5 — Linux PG Backlog Migration Apply Audit

## §1 Linux PG runtime state（empirical query 結果）

### 1.1 `_sqlx_migrations` applied snapshot（2026-05-16 ssh trade-core）

```sql
SELECT MAX(version) FROM _sqlx_migrations WHERE success=true;
-- 結果：max_applied = 90
```

完整 applied 序列（87 rows，from V001..V90）：
```
... 78 79 80 [82] 83 84 85 86 87 88 89 90
```
**V081 跳號（V080 → V082 直接連跳）；V091/V092/V093 不在表中。**

Top 5 most-recent applied:
| version | description | installed_on | success |
|---|---|---|---|
| 90 | governance unblock candidates | 2026-05-10 22:57 | t |
| 89 | governance canary stage metric seed | 2026-05-10 23:30 | t |
| 88 | panel btc lead lag panel | 2026-05-10 22:47 | t |
| 87 | panel oi delta panel | 2026-05-10 22:47 | t |
| 86 | governance reject close reason code | 2026-05-10 22:57 | t |

### 1.2 Engine runtime 狀態

- `systemctl --user status openclaw-engine` → `Unit not found`
- `ls /tmp/openclaw/*.flag /tmp/openclaw/*.pid` → 全不存在
- `ps -ef | grep openclaw_engine` → 0 hit

**結論**：engine 目前不在跑（與 TODO v32 「runtime binary `7b33ab2e` source/docs/probe-only」相符）。Engine 下次 spawn 將觸發 sqlx migrate run，必處理 backlog。

### 1.3 `OPENCLAW_AUTO_MIGRATE` flag

```bash
grep OPENCLAW_AUTO_MIGRATE ~/.openclaw_secrets/environment_files/basic_system_services.env
→ no_flag（未設）
```

**結論**：engine restart 不會自動 sqlx migrate run；必走 `bash helper_scripts/linux_bootstrap_db.sh --apply` 或顯式設 flag。

### 1.4 V091 / V093 schema 狀態 — partial manual apply 偵測

**V091 (chk_reason_code_mutually_exclusive)** ✅ 已存在於 `learning.decision_features`：
```
constraint def: CHECK ((NOT ((reject_reason_code IS NOT NULL) AND (close_reason_code IS NOT NULL))))
convalidated:    t  ← 已 VALIDATE（file spec 是 NOT VALID + D+2 後 manual VALIDATE）
```

**V093 schema** ✅ 已 partial apply：
- `chk_decision_features_evaluations_outcome` enum 8 values 包含 `'oi_panel_unavailable'` ✅
- `chk_decision_features_evaluations_evidence_tier` enum 3 values 包含 `'panel_fail_closed'` ✅
- `chk_decision_features_evaluations_side` enum `(-1, 0, 1)` 包含 `side=0` ✅

**V092 (continuous_aggregate)** ❌ 完全沒 apply：
```sql
SELECT view_name FROM timescaledb_information.continuous_aggregates → 0 rows
SELECT matviewname FROM pg_matviews WHERE schemaname='panel' AND matviewname LIKE 'funding_rates_panel%' OR matviewname LIKE 'oi_delta_panel%' → 0 rows
```

`timescaledb` 2.26.1 extension 存在；source tables `panel.funding_rates_panel` + `panel.oi_delta_panel` 都在 → V092 prerequisites OK，未跑純粹 migration runner 沒到。

---

## §2 Source tree migration files inventory

```
V080__governance_canary_stage.sql               ✓ applied 2026-05-10
[V081 不存在 — 合法跳號]
V082__decision_features_evaluations_split.sql   ✓ applied 2026-05-10
V083__fills_entry_context_id_close_check.sql    ✓ applied 2026-05-10
V084..V090                                       ✓ applied 2026-05-10
V091__decision_features_reject_close_mutex_check.sql      ❌ not in sqlx (DB schema partial-applied)
V092__panel_continuous_aggregates.sql                     ❌ not in sqlx (DB 0 matview)
V093__decision_features_evaluations_panel_fail_closed.sql ❌ not in sqlx (DB schema partial-applied)
```

V091 = 215 LOC / V092 = 217 LOC / V093 = 88 LOC。V091 idempotency guard count 7 / V092 = 8 / V093 = 6（全有 `IF NOT EXISTS` + `RAISE EXCEPTION` + `DROP CONSTRAINT IF EXISTS` 對應路徑）。

---

## §3 Gap identification per migration

### 3.1 V081 — DEAD SLOT（confirmed not a gap）

Source tree 無 `V081*.sql`；`_sqlx_migrations` 無 row 80→82 連跳合法。sqlx 對非連續 version 不 enforce sequential；deploy 階段 `bootstrap_db.sh` 對任何缺號自動 skip。**V081 不是 backlog，是設計上的 dead slot。**

### 3.2 V091 — chk_reason_code_mutually_exclusive — **SCHEMA EXISTS / sqlx 漏 record**

| Aspect | 狀態 |
|---|---|
| DB constraint 物理存在 | ✅ |
| 已 VALIDATE | ✅ convalidated=t |
| `_sqlx_migrations` 有 record | ❌ |
| File idempotent design | ✅（IF NOT EXISTS / 7 guards） |

**風險**：engine restart sqlx migrate run 將嘗試 apply V091 file → 因 idempotent design 應 PASS（`ALTER TABLE ... ADD CONSTRAINT IF NOT EXISTS` semantic 或 wrapped in DO block + EXCEPTION handler）；但 sqlx 計算 file checksum 寫入 `_sqlx_migrations` 完成 record。**Apply 風險：LOW（純 metadata 補登）**。

**反邏輯**：若 V091 file 之後再被 edit 過 → checksum drift → engine restart sqlx migrate 仍 panic（per project_2026_05_02_p0_sqlx_hash_drift）。需 Mac local file vs 預期內容 review。Linux file mtime `2026-05-10 23:43` 顯示落地後沒再改。

### 3.3 V092 — panel continuous_aggregates — **NOT APPLIED（real gap）**

| Aspect | 狀態 |
|---|---|
| DB matview 物理存在 | ❌（0 funding_rates_panel_* / 0 oi_delta_panel_*） |
| `_sqlx_migrations` 有 record | ❌ |
| Prereq tables (`panel.funding_rates_panel` + `panel.oi_delta_panel`) | ✅ 存在 |
| `timescaledb` extension | ✅ 2.26.1 |
| File idempotent design | ✅（IF NOT EXISTS / 8 guards / WITH NO DATA 不阻塞 boot） |

**風險**：apply 期 `WITH NO DATA` 設計避開 boot 阻塞 10-30s；後續 `add_continuous_aggregate_policy(..., if_not_exists => TRUE)` 設 refresh schedule。**Apply 風險：LOW-MEDIUM**（首次 apply 會建 6 matview + 6 policy；DB schema visible side effect 比 V091/V093 大；但 W1 ML training / monitoring 路徑等的 sub-task 3 真實 IMPL evidence）。

**邏輯結論**：V092 是 W1 sub-task 3 (E1-γ, 2026-05-11) 的真實 deploy gap — 文件落地後 D+1+ deploy 沒進行 → 一直沒 apply 過。

### 3.4 V093 — decision_features_evaluations panel fail-closed — **SCHEMA EXISTS / sqlx 漏 record**

| Aspect | 狀態 |
|---|---|
| DB enum constraint 三 (outcome/evidence_tier/side) | ✅ 已對齊 file spec |
| `_sqlx_migrations` 有 record | ❌ |
| File idempotent design | ✅（DROP CONSTRAINT IF EXISTS + ADD + Guard A） |
| File mtime | `2026-05-14 10:50`（recent — Wave 1.5 land 中） |

**風險**：apply 期 `DROP CONSTRAINT IF EXISTS chk_decision_features_evaluations_outcome` 後 `ADD CONSTRAINT` 同名 enum — semantic identical → result 不變。**Apply 風險：LOW**（純 metadata 補登 + constraint drop/re-add 0 row violation）。

**反邏輯**：V093 file 2026-05-14 修過（per F-FA-3 PA report Wave 1 Track A4 chain），但 DB schema constraint 早於文件 final 就 partial-apply（時序矛盾）。可能歷史：Wave 1 IMPL phase 某 sub-agent 手動執行 V093 早期 draft 的 SQL；後續 file polish 不影響 schema 結果。**Mac source file 內容 ↔ Linux DB schema 必 cross-verify 才 apply**。

---

## §4 V094 IMPL kickoff 阻塞性評估

### 4.1 V094 deploy 路徑 dependency

V094 IMPL kickoff 後 deploy 階段（Wave 4+ 派 E1 5-worktree）會走：
```
restart_all --rebuild
  → engine binary rebuild
  → engine boot
    → sqlx migrate run (若 OPENCLAW_AUTO_MIGRATE=1 或 manual bootstrap_db.sh --apply)
      → 找出 missing version → V091, V092, V093, V094 全 apply
      → 計算 file checksum 寫 _sqlx_migrations
```

### 4.2 不補 backlog 直接 deploy V094 的風險

| 情境 | 結果 |
|---|---|
| OPENCLAW_AUTO_MIGRATE=0（current state）+ manual sqlx migrate skip | V094 schema 物理 apply (manual psql -f V094.sql 路徑) → sqlx record 缺 V091/V092/V093/V094 全部 → V091/V093 schema drift 持續 + V092 matview 仍 0 + IMPL kickoff 後續 restart 引爆 sqlx panic |
| OPENCLAW_AUTO_MIGRATE=1 開啟 | engine boot 嘗試 apply V091 → idempotent PASS → V092 嘗試 apply → 真 IMPL → V093 嘗試 apply → idempotent PASS → V094 apply。**但 V091/V093 file 若 已 edit 過（checksum drift）→ engine boot panic** |

### 4.3 阻塞判定

**V094 IMPL kickoff 在 spec / PA verdict / writer upgrade design 層面 NOT blocked**（已 Wave 2a closed）。
**V094 deploy 階段 BLOCKED by V091/V092/V093 backlog**：必須處理乾淨後才能 deploy V094。

但 **IMPL phase（E1 worktree A+B 並行 + C 串行）本身可開工**（純源碼 + Mac 端開發 + Linux PG dry-run × 2 round 在 staging path）— deploy `restart_all --rebuild` 前必補完 backlog。

---

## §5 Recommended apply protocol

per CLAUDE.md §七 SQL migration 規範 + `feedback_v_migration_pg_dry_run.md` SOP：

### 5.1 Pre-apply preparation（PA + operator co-handle）

1. **PA：Mac local file content vs Linux DB current schema 對比 verify**
   - V091 file → 預期 DB constraint def → 確認 `CHECK ((NOT ((reject_reason_code IS NOT NULL) AND (close_reason_code IS NOT NULL))))`（Linux empirical 已驗 ✅）
   - V092 file → 預期 6 matview 名稱 + add_continuous_aggregate_policy params
   - V093 file → 預期 3 enum 加新值
2. **PA：grep `git log --oneline -- sql/migrations/V091*.sql V092*.sql V093*.sql`** 確認 file 不曾被 mutate（避免 checksum drift surprise）
3. **operator：確認 24h `panel.funding_rates_panel` + `panel.oi_delta_panel` 有 row** → V092 matview WITH NO DATA refresh 後將 ingest

### 5.2 Apply 順序（PM + operator）

**操作員執行 — PA 不直接動 runtime**：

#### Step 1：V091 sqlx record 補登
```bash
ssh trade-core
cd ~/BybitOpenClaw/srv
bash helper_scripts/linux_bootstrap_db.sh --dry-run V091  # PA 設計：dry-run mode 應該 detect schema drift + 提示
# 若 dry-run report「constraint already exists, no schema change」→ proceed
bash helper_scripts/linux_bootstrap_db.sh --apply V091
# 預期：sqlx INSERT _sqlx_migrations row + 0 schema change
```

#### Step 2：V092 真 IMPL apply（critical step）
```bash
# Round 1 dry-run（per V094 spec §4 mandatory）
psql -h localhost -U trading_admin -d trading_ai -f sql/migrations/V092__panel_continuous_aggregates.sql \
  | tee /tmp/v092_round1.log

# verify
psql -c "SELECT matviewname FROM pg_matviews WHERE schemaname='panel' ORDER BY matviewname"
# 預期 6 row：funding_rates_panel_5m/15m/1h + oi_delta_panel_5m/15m/1h

psql -c "SELECT view_name FROM timescaledb_information.continuous_aggregates ORDER BY view_name"
# 預期 6 row

# Round 2 idempotency
psql -h localhost -U trading_admin -d trading_ai -f sql/migrations/V092__panel_continuous_aggregates.sql \
  | tee /tmp/v092_round2.log
diff /tmp/v092_round1.log /tmp/v092_round2.log  # NOTICE skip pattern 應對齊；無 RAISE EXCEPTION
```

#### Step 3：V093 sqlx record 補登
```bash
bash helper_scripts/linux_bootstrap_db.sh --dry-run V093
bash helper_scripts/linux_bootstrap_db.sh --apply V093
# 預期：DROP CONSTRAINT 後 re-ADD 同名同 def → 0 row violation；sqlx INSERT row
```

#### Step 4：全 verify
```bash
psql -c "SELECT version FROM _sqlx_migrations ORDER BY version DESC LIMIT 5"
# 預期：93, 92, 91, 90, 89
```

### 5.3 sqlx checksum repair 觸發條件（per project_2026_05_02_p0_sqlx_hash_drift）

若上述 step 任一觸發 `sqlx migrate` error `migration X was previously applied but has been modified`：
```bash
cargo run --release --bin repair_migration_checksum -- --version 91
cargo run --release --bin repair_migration_checksum -- --version 92
cargo run --release --bin repair_migration_checksum -- --version 93
```
**強烈建議：每個 step 後 cargo test PASS ≠ runtime sqlx migrate 驗證 — 必跑 `cargo run --release --bin openclaw_engine -- --check-migrations` 或 engine 短啟動 2 min 觀察 panic 沒觸發。**

### 5.4 Rollback 路徑

- V091 / V093 metadata 補登 fail → manual `DELETE FROM _sqlx_migrations WHERE version IN (91, 93)` 重置；schema 不動
- V092 matview apply fail → `DROP MATERIALIZED VIEW IF EXISTS panel.funding_rates_panel_5m CASCADE` 等逐個 drop；source table 不影響
- V094 IMPL kickoff 不受 backlog rollback 影響（schema 改動分離）

### 5.5 owner / 工時估算

| Step | Owner | 估時 | 風險 |
|---|---|---|---|
| 5.1 Mac local file content verify + git log | PA | 0.3h | LOW（純 source review） |
| 5.2 Step 1 V091 metadata 補登 | operator (PM 監督) | 0.2h | LOW |
| 5.2 Step 2 V092 真 IMPL × 2 round dry-run | operator (PM + PA verify result) | 1.0h | LOW-MEDIUM（首次 matview build） |
| 5.2 Step 3 V093 metadata 補登 | operator (PM 監督) | 0.2h | LOW |
| 5.2 Step 4 全 verify + healthcheck rerun | operator | 0.3h | LOW |
| **Total** | mixed | **~2h** | LOW-MEDIUM overall |

---

## §6 PA verdict

### 6.1 結論 = **NEEDS-ACTION**

**V094 IMPL kickoff（Wave 4+ E1 worktree dispatch）NOT BLOCKED** — IMPL phase 純源碼開發 + Linux PG dry-run × 2 round 在 staging path，本 audit 識別的 backlog gap 不影響 spec finalize 或 E1 IMPL 開工。

**V094 deploy（`restart_all --rebuild` + engine boot + sqlx migrate run）BLOCKED 直到 §5.2 protocol 跑完**：必補 V091 + V092 + V093 backlog。

### 6.2 16 根原則合規

per skill `16-root-principles-checklist`：
- 本 audit 純 read-only，不觸 §四 任何硬邊界
- 不觸 DOC-08 §12 9 安全不變量
- 不觸 16 原則（純治理/SOP 補強）
- 評級 = **A 級**（16/16 合規 + 0 硬邊界觸碰）

### 6.3 派發 Action 清單

| Action | Owner | Priority | 上游 trigger |
|---|---|---|---|
| 本 PA report sign-off | PM | P0 | 接 PM 派發回應 |
| 把 §5 protocol 寫成 Wave 3.5 RUN PLAN（短 spec） | PA 或 PM | P0 | sign-off 後 |
| TODO §11.5 Wave 3.5 row → IN_PROGRESS（owner = operator + PM） | PM | P0 | sign-off 後 |
| 執行 §5.2 Step 1-4 | operator + PM | P0 | Wave 3.5 RUN PLAN 落地 |
| Wave 4 IMPL kickoff（V094 E1 5-worktree dispatch）| PM | P1 | 3-gate 解除 + Wave 3.5 完成 |
| V094 deploy gate（必驗 V091/V092/V093/V094 全 `_sqlx_migrations`） | E2 review | P1 | E1 IMPL 完 + before restart |
| Healthcheck rerun（[62][63][64][65] + 涵蓋 V092 matview 可讀） | operator | P2 | V092 apply 後 D+1 |

### 6.4 Confidence

- **HIGH** V091/V093 schema drift identification（empirical convalidated=t / pg_get_constraintdef 對齊 file spec）
- **HIGH** V092 not applied confirmation（0 matview + 0 continuous_aggregate empirical）
- **HIGH** V081 dead slot confirmation（source tree + sqlx 雙缺）
- **HIGH** Engine not running（systemctl + flag + pid 三證據）
- **HIGH** OPENCLAW_AUTO_MIGRATE not set（env file 直 grep）
- **MEDIUM** V091/V093 file mtime 後是否再被 edit → 必 git log verify（§5.1 Step 2）；目前推斷未 mutate（與 schema 對齊）
- **MEDIUM** V092 真 IMPL apply 期 matview build 真實工時（首次 build 視 panel.* 表 row 量；24h 0 panel row → WITH NO DATA 0 阻塞；若 panel ingest 已 backfill 7d row → 可能 5-10s build）

### 6.5 架構教訓 25

**sqlx_migrations metadata 與 DB physical schema 可能 drift — 此 drift 是 silent，發現靠 PA cross-section empirical query**。本 audit V091/V093 case：schema 物理上已 apply（constraint 全在 + convalidated=t），但 `_sqlx_migrations` 缺 row。可能成因：
1. 歷史 sub-agent 手動 psql -f V091.sql 跑（沒走 sqlx migrate）
2. partial apply 期間 sqlx INSERT fail（unlikely - transaction atomic）
3. backup/restore 期間 metadata 表沒 sync

**SOP 加強建議**：所有 V### migration apply 必走 `helper_scripts/linux_bootstrap_db.sh` 統一入口；嚴禁 sub-agent 直接 psql -f 跑 migration file。如必須 manual apply（emergency），必同 commit `INSERT INTO _sqlx_migrations` 維持 metadata 一致。E2 review 加 grep 規則：`grep -rE 'psql.*-f.*sql/migrations/V[0-9]+' .codex/ docs/CCAgentWorkSpace/*/workspace/reports/` → 命中要求顯式 metadata maintenance evidence。

### 6.6 架構教訓 26

**dead slot (V081) 是合法的 numbering 設計 — 不要 backfill「補洞」**。sqlx 對非連續 version 不 enforce sequential apply；V080 → V082 直接連跳完全合法（V081 可能歷史上被 abort / merge conflict 占號 / spec rename 等原因）。本 audit 確認 V081 既不在 source 也不在 sqlx → 純 dead slot，0 backlog gap。**PM/PA 對 missing version 必先檢查 source tree 是否有對應 file 才判斷 backlog**；無 file = dead slot；有 file 但 sqlx 缺 = backlog gap。

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--wave_3_5_linux_pg_backlog_migration_audit.md`
